from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from django.utils import timezone
from django.conf import settings
from .models import Ticket, DoorStaffCode, TicketTransfer
from .serializers import (
    TicketSerializer, PurchaseSerializer, TransferSerializer,
    VerifyTicketSerializer, DoorStaffCodeSerializer, verify_dynamic_qr_token
)
from events.models import Event
from accounts.models import User
from payments.models import Wallet, Transaction
from utils.emails import notify_ticket_purchase, notify_ticket_transfer
from utils.blockchain import mint_ticket_nft_async, get_polygon_explorer_url
from decimal import Decimal
import random
import string
import requests
import qrcode
from io import BytesIO
import base64
import cloudinary.uploader


# ── Paystack verification helper ─────────────────────────────
def verify_paystack_payment(reference, expected_amount_kobo):
    """
    Verify payment with Paystack API.
    Returns True if payment is confirmed and amount matches.
    """
    secret_key = getattr(settings, 'PAYSTACK_SECRET_KEY', '')
    if not secret_key:
        # No Paystack configured — allow in dev, block in prod
        print("⚠️  PAYSTACK_SECRET_KEY not set — skipping payment verification (dev mode)")
        return True

    try:
        resp = requests.get(
            f"https://api.paystack.co/transaction/verify/{reference}",
            headers={"Authorization": f"Bearer {secret_key}"},
            timeout=15,
        )
        data = resp.json()

        if not data.get('status'):
            print(f"Paystack verify failed: {data.get('message')}")
            return False

        tx = data.get('data', {})

        if tx.get('status') != 'success':
            print(f"Paystack payment not successful: {tx.get('status')}")
            return False

        # Amount check — Paystack uses kobo (pesewas for GHS)
        paid_amount = tx.get('amount', 0)
        if paid_amount < expected_amount_kobo:
            print(f"Amount mismatch: paid {paid_amount}, expected {expected_amount_kobo}")
            return False

        return True

    except Exception as e:
        print(f"Paystack verify error: {e}")
        # On connection error — fail safe (block purchase)
        return False


# ── QR generation helper ──────────────────────────────────────
def generate_and_upload_qr(ticket):
    """Generate QR, upload to Cloudinary, return url and base64."""
    qr_content = ticket.qr_data
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=10,
        border=4,
    )
    qr.add_data(qr_content)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buffer = BytesIO()
    img.save(buffer, format='PNG')
    buffer.seek(0)
    qr_base64 = base64.b64encode(buffer.getvalue()).decode()

    try:
        buffer.seek(0)
        result = cloudinary.uploader.upload(
            buffer,
            folder="master_events/qr_codes",
            public_id=f"qr_{ticket.ticket_id}",
            resource_type="image",
            overwrite=True,
        )
        url = result['secure_url']
        print(f"✅ QR uploaded to Cloudinary: {url}")
        return url, qr_base64
    except Exception as e:
        print(f"⚠️ QR Cloudinary upload failed: {e}")
        return None, qr_base64


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def my_tickets(request):
    tickets = Ticket.objects.filter(
        owner=request.user
    ).exclude(status='transferred').select_related('event', 'owner')
    serializer = TicketSerializer(tickets, many=True, context={'request': request})
    return Response(serializer.data)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def purchase_ticket(request):
    serializer = PurchaseSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    data = serializer.validated_data

    # ── Step 1: Validate event ────────────────────────────────
    try:
        event = Event.objects.get(pk=data['event_id'], is_active=True, sales_open=True)
    except Event.DoesNotExist:
        return Response(
            {'error': 'Event not found or sales closed'},
            status=status.HTTP_404_NOT_FOUND
        )

    if event.tickets_remaining < data['quantity']:
        return Response(
            {'error': 'Not enough tickets available'},
            status=status.HTTP_400_BAD_REQUEST
        )

    total          = Decimal(str(float(event.price) * data['quantity']))
    total_pesewas  = int(total * 100)  # Paystack uses smallest currency unit

    # ── Step 2: Verify payment with Paystack ─────────────────
    payment_ref = data['payment_reference']
    if not verify_paystack_payment(payment_ref, total_pesewas):
        return Response(
            {'error': 'Payment could not be verified. Please complete payment first.'},
            status=status.HTTP_402_PAYMENT_REQUIRED
        )

    # ── Step 3: Prevent duplicate purchase with same reference ─
    if Ticket.objects.filter(payment_reference=payment_ref).exists():
        return Response(
            {'error': 'This payment reference has already been used.'},
            status=status.HTTP_409_CONFLICT
        )

    # ── Step 4: Create ticket ─────────────────────────────────
    ticket = Ticket(
        event=event,
        owner=request.user,
        original_buyer=request.user,
        quantity=data['quantity'],
        price_paid=total,
        payment_reference=payment_ref,
        status='active',
    )
    ticket.save()

    # ── Step 5: Generate + upload QR ─────────────────────────
    qr_url, qr_base64 = generate_and_upload_qr(ticket)
    if qr_url:
        ticket.qr_image = qr_url
        ticket.save(update_fields=['qr_image'])

    # ── Step 6: Update event ticket count ─────────────────────
    event.tickets_sold += data['quantity']
    event.save()

    # ── Step 7: Credit organizer wallet (95%) ─────────────────
    organizer_wallet, _ = Wallet.objects.get_or_create(user=event.organizer)
    organizer_amount     = total * Decimal('0.95')
    organizer_wallet.balance     += organizer_amount
    organizer_wallet.total_earned += organizer_amount
    organizer_wallet.save()

    Transaction.objects.create(
        wallet=organizer_wallet,
        type='sale',
        amount=organizer_amount,
        description=f"{data['quantity']}x {event.name}",
        reference=payment_ref,
        status='completed',
    )

    # ── Step 8: Send confirmation email ───────────────────────
    try:
        notify_ticket_purchase(ticket)
    except Exception as e:
        print(f"Email notification failed: {e}")

    # ── Step 9: Return ticket data ────────────────────────────
    ticket_data             = TicketSerializer(ticket, context={'request': request}).data
    ticket_data['qr_base64'] = qr_base64

    # ── Step 10: Mint NFT in background ──────────────────────
    try:
        owner_wallet = getattr(request.user, 'wallet_address', None)

        def on_mint_success(nft_result):
            try:
                from tickets.models import Ticket as TicketModel
                t = TicketModel.objects.get(pk=ticket.pk)
                t.nft_token_id    = nft_result['token_id']
                t.nft_tx_hash     = nft_result['tx_hash']
                t.nft_token_uri   = nft_result['token_uri']
                t.nft_mint_failed = False
                t.save(update_fields=['nft_token_id', 'nft_tx_hash', 'nft_token_uri', 'nft_mint_failed'])
                print(f"✅ NFT saved for ticket {t.ticket_id}: token={nft_result['token_id']}")
            except Exception as e:
                print(f"Error saving NFT result: {e}")

        mint_ticket_nft_async(ticket, owner_wallet, callback=on_mint_success)
        ticket_data['nft_minting'] = True
        ticket_data['message']     = 'Ticket purchased! NFT minting on Polygon...'
    except Exception as e:
        print(f"NFT mint init failed (non-critical): {e}")

    return Response(ticket_data, status=status.HTTP_201_CREATED)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def transfer_ticket(request):
    serializer = TransferSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    data = serializer.validated_data

    try:
        ticket = Ticket.objects.get(
            ticket_id=data['ticket_id'],
            owner=request.user,
            status='active'
        )
    except Ticket.DoesNotExist:
        return Response(
            {'error': 'Ticket not found or not active'},
            status=status.HTTP_404_NOT_FOUND
        )

    try:
        to_user = User.objects.get(email=data['to_email'])
    except User.DoesNotExist:
        return Response(
            {'error': 'No Master Events account found with that email'},
            status=status.HTTP_404_NOT_FOUND
        )

    if to_user == request.user:
        return Response(
            {'error': 'Cannot transfer to yourself'},
            status=status.HTTP_400_BAD_REQUEST
        )

    # ── Record transfer history ───────────────────────────────
    TicketTransfer.objects.create(
        ticket=ticket,
        from_user=request.user,
        to_user=to_user
    )

    # ── Void old ticket ───────────────────────────────────────
    ticket.owner  = to_user
    ticket.status = 'transferred'
    ticket.save()

    # ── Create new ticket for recipient ──────────────────────
    new_ticket = Ticket(
        event=ticket.event,
        owner=to_user,
        original_buyer=ticket.original_buyer,
        quantity=ticket.quantity,
        price_paid=ticket.price_paid,
        status='active',
        is_resale=True,
    )
    new_ticket.save()

    # ── Generate new QR for recipient ────────────────────────
    qr_url, _ = generate_and_upload_qr(new_ticket)
    if qr_url:
        new_ticket.qr_image = qr_url
        new_ticket.save(update_fields=['qr_image'])

    # ── Notify both parties ───────────────────────────────────
    try:
        notify_ticket_transfer(ticket, request.user, to_user)
    except Exception as e:
        print(f"Transfer email failed: {e}")

    # ── On-chain NFT transfer (if wallet addresses exist) ─────
    try:
        if ticket.nft_token_id and to_user.wallet_address and request.user.wallet_address:
            from utils.blockchain import transfer_ticket_nft
            transfer_ticket_nft(
                ticket.nft_token_id,
                request.user.wallet_address,
                to_user.wallet_address
            )
        elif ticket.nft_token_id:
            # Mint a new NFT for recipient if no wallet binding
            def on_new_mint(nft_result):
                try:
                    from tickets.models import Ticket as TicketModel
                    t = TicketModel.objects.get(pk=new_ticket.pk)
                    t.nft_token_id  = nft_result['token_id']
                    t.nft_tx_hash   = nft_result['tx_hash']
                    t.nft_token_uri = nft_result['token_uri']
                    t.save(update_fields=['nft_token_id', 'nft_tx_hash', 'nft_token_uri'])
                except Exception as e:
                    print(f"Transfer NFT save error: {e}")
            mint_ticket_nft_async(new_ticket, callback=on_new_mint)
    except Exception as e:
        print(f"NFT transfer failed (non-critical): {e}")

    return Response({
        'message':    'Ticket transferred successfully',
        'new_ticket': TicketSerializer(new_ticket, context={'request': request}).data
    })


def _find_ticket(qr_data):
    """Shared ticket lookup — 4 strategies."""
    # Strategy 1: Dynamic HMAC QR
    ticket_id_from_qr, _ = verify_dynamic_qr_token(qr_data)
    if ticket_id_from_qr:
        try:
            return Ticket.objects.select_related('event', 'owner').get(
                ticket_id=ticket_id_from_qr
            )
        except Ticket.DoesNotExist:
            pass

    # Strategy 2: Static qr_data
    try:
        return Ticket.objects.select_related('event', 'owner').get(qr_data=qr_data)
    except Ticket.DoesNotExist:
        pass

    # Strategy 3: Direct ticket_id
    try:
        return Ticket.objects.select_related('event', 'owner').get(
            ticket_id=qr_data.upper()
        )
    except Ticket.DoesNotExist:
        pass

    # Strategy 4: MASTER-EVENTS UUID format
    if qr_data.startswith('MASTER-EVENTS:'):
        try:
            parts = qr_data.split(':')
            if len(parts) >= 2:
                return Ticket.objects.select_related('event', 'owner').get(id=parts[1])
        except Exception:
            pass

    return None


@api_view(['POST'])
@permission_classes([AllowAny])
def public_scan_ticket(request):
    """
    Public QR scan — read-only, no redemption.
    Shows ticket owner info for anyone with a phone camera.
    """
    qr_data = request.data.get('qr_data', '').strip()
    if not qr_data:
        return Response(
            {'valid': False, 'reason': 'No QR data provided'},
            status=400
        )

    ticket = _find_ticket(qr_data)
    if not ticket:
        return Response(
            {'valid': False, 'reason': 'Ticket not found or QR expired'},
            status=404
        )

    owner = ticket.owner
    return Response({
        'valid':        True,
        'public_scan':  True,
        'ticket_id':    str(ticket.ticket_id),
        'status':       ticket.status,
        'holder_name':  owner.get_full_name() or owner.email,
        'holder_email': owner.email,
        'event_name':   ticket.event.name,
        'event_date':   str(ticket.event.date),
        'event_venue':  ticket.event.venue,
        'event_city':   getattr(ticket.event, 'city', 'Ghana'),
        'quantity':     ticket.quantity,
        'is_transfer':  ticket.is_resale,
        'nft_token_id': ticket.nft_token_id,
        'redeemed_at':  ticket.redeemed_at,
        'message':      f"🎟️ Ticket belongs to {owner.get_full_name() or owner.email}",
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def verify_ticket(request):
    """
    Door staff / organizer scan — validates AND redeems the ticket.
    Requires authentication. One-time use.
    """
    serializer = VerifyTicketSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=400)

    data    = serializer.validated_data
    qr_data = data['qr_data'].strip()
    event_id = data.get('event_id', 0)

    ticket = _find_ticket(qr_data)

    if not ticket:
        return Response(
            {'valid': False, 'reason': 'Ticket not found or QR expired'},
            status=404
        )

    # Event check
    if event_id and event_id != 0 and ticket.event.id != event_id:
        return Response({
            'valid':      False,
            'reason':     f'Wrong event — ticket is for {ticket.event.name}',
            'holder':     ticket.owner.get_full_name() or ticket.owner.email,
            'event_name': ticket.event.name,
        })

    # Already redeemed
    if ticket.status == 'redeemed':
        return Response({
            'valid':       False,
            'reason':      'Already redeemed',
            'holder':      ticket.owner.get_full_name() or ticket.owner.email,
            'redeemed_at': ticket.redeemed_at,
            'event_name':  ticket.event.name,
        })

    # Invalid status
    if ticket.status not in ['active', 'resale']:
        return Response({
            'valid':      False,
            'reason':     f'Ticket is {ticket.status}',
            'holder':     ticket.owner.get_full_name() or ticket.owner.email,
            'event_name': ticket.event.name,
        })

    # ✅ Admit
    ticket.status      = 'redeemed'
    ticket.redeemed_at = timezone.now()
    ticket.save()

    return Response({
        'valid':          True,
        'holder':         ticket.owner.get_full_name() or ticket.owner.email,
        'holder_email':   ticket.owner.email,
        'ticket_id':      str(ticket.ticket_id),
        'event':          ticket.event.name,
        'event_name':     ticket.event.name,
        'quantity':       ticket.quantity,
        'is_transfer':    ticket.is_resale,
        'nft_token_id':   ticket.nft_token_id,
        'redeemed_at':    ticket.redeemed_at,
        'blockchain_url': get_polygon_explorer_url(ticket.nft_tx_hash) if ticket.nft_tx_hash else None,
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def generate_door_code(request, event_id):
    try:
        event = Event.objects.get(pk=event_id)
    except Event.DoesNotExist:
        return Response(
            {'error': f'Event {event_id} not found'},
            status=status.HTTP_404_NOT_FOUND
        )

    if event.organizer != request.user:
        return Response(
            {'error': 'You are not the organizer of this event'},
            status=status.HTTP_403_FORBIDDEN
        )

    code      = 'DOOR-' + ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    door_code = DoorStaffCode.objects.create(event=event, code=code, created_by=request.user)
    return Response(DoorStaffCodeSerializer(door_code).data, status=status.HTTP_201_CREATED)


@api_view(['POST'])
@permission_classes([AllowAny])
def door_staff_login(request):
    code = request.data.get('code', '').upper().strip()
    try:
        door_code = DoorStaffCode.objects.get(code=code, is_active=True)
    except DoorStaffCode.DoesNotExist:
        return Response(
            {'error': 'Invalid or expired door staff code'},
            status=status.HTTP_400_BAD_REQUEST
        )

    # ── Mark code as used — single use only ──────────────────
    door_code.is_active = False
    door_code.save(update_fields=['is_active'])

    return Response({
        'valid':      True,
        'event_id':   door_code.event.id,
        'event_name': door_code.event.name,
        'code':       door_code.code,
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def event_tickets(request, event_id):
    try:
        event = Event.objects.get(pk=event_id, organizer=request.user)
    except Event.DoesNotExist:
        return Response({'error': 'Event not found'}, status=status.HTTP_404_NOT_FOUND)

    tickets = Ticket.objects.filter(event=event).select_related('owner')
    serializer = TicketSerializer(tickets, many=True, context={'request': request})
    return Response(serializer.data)




@api_view(['GET'])
@permission_classes([AllowAny])
def nft_metadata(request, ticket_id):
    """
    Public NFT metadata endpoint — readable by OpenSea, Polygonscan.
    Returns JSON metadata for a ticket's NFT.
    """
    try:
        ticket = Ticket.objects.select_related('event').get(ticket_id=ticket_id)
    except Ticket.DoesNotExist:
        return Response({'error': 'Not found'}, status=404)

    from utils.blockchain import build_ticket_metadata
    metadata = build_ticket_metadata(ticket)
    return Response(metadata)