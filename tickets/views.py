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
from decimal import Decimal
import random
import string
import requests
from django_ratelimit.decorators import ratelimit
from django_q.tasks import async_task
import qrcode
from io import BytesIO
import base64
import cloudinary.uploader
from django.utils import timezone
from datetime import timedelta
from django.db import transaction



# ── Paystack verification ─────────────────────────────────────
def verify_paystack_payment(reference, expected_amount_pesewas):
    secret_key = getattr(settings, 'PAYSTACK_SECRET_KEY', '')
    if not secret_key:
        print("⚠️ PAYSTACK_SECRET_KEY not set — skipping verification (dev mode)")
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
        paid_amount = tx.get('amount', 0)
        if paid_amount < expected_amount_pesewas:
            print(f"Amount mismatch: paid {paid_amount}, expected {expected_amount_pesewas}")
            return False
        return True
    except Exception as e:
        print(f"Paystack verify error: {e}")
        return False


# ── QR generation helper ──────────────────────────────────────
def generate_and_upload_qr(ticket):
    qr_content = ticket.qr_data
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=10,
        border=4,
    )
    qr.add_data(qr_content)
    qr.make(fit=True)
    img    = qr.make_image(fill_color="black", back_color="white")
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


# ── My tickets ────────────────────────────────────────────────
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def my_tickets(request):
    tickets = Ticket.objects.filter(
        owner=request.user
    ).exclude(status='transferred').select_related('event', 'owner')
    serializer = TicketSerializer(tickets, many=True, context={'request': request})
    return Response(serializer.data)


# ── Purchase ticket ───────────────────────────────────────────
@api_view(['POST'])
@permission_classes([IsAuthenticated])
@ratelimit(key='user', rate='10/m', method='POST', block=False)
def purchase_ticket(request):
    if getattr(request, 'limited', False):
        return Response({'error': 'Too many purchase attempts.'}, status=429)

    serializer = PurchaseSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=400)

    data = serializer.validated_data

    total         = None
    total_pesewas = None

    # ── Verify payment first (outside lock) ───────────────────
    try:
        event = Event.objects.get(pk=data['event_id'], is_active=True, sales_open=True)
    except Event.DoesNotExist:
        return Response({'error': 'Event not found or sales closed'}, status=404)

    total         = Decimal(str(float(event.price) * data['quantity']))
    total_pesewas = int(total * 100)
    payment_ref   = data['payment_reference']

    if not verify_paystack_payment(payment_ref, total_pesewas):
        return Response({'error': 'Payment could not be verified.'}, status=402)

    if Ticket.objects.filter(payment_reference=payment_ref).exists():
        return Response({'error': 'Payment reference already used.'}, status=409)

    # ── Atomic lock — prevent overselling ────────────────────
    try:
        with transaction.atomic():
            event = Event.objects.select_for_update().get(
                pk=data['event_id'], is_active=True, sales_open=True
            )
            if event.tickets_remaining < data['quantity']:
                return Response({'error': 'Not enough tickets available'}, status=400)

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

            event.tickets_sold += data['quantity']
            event.save(update_fields=['tickets_sold'])

            organizer_wallet, _ = Wallet.objects.get_or_create(user=event.organizer)
            organizer_amount     = total * Decimal('0.95')
            organizer_wallet.balance      += organizer_amount
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

    except Exception as e:
        print(f"Purchase atomic error: {e}")
        return Response({'error': 'Purchase failed. Please try again.'}, status=500)

    # ── Outside lock — QR + email + NFT ──────────────────────
    qr_url, qr_base64 = generate_and_upload_qr(ticket)
    if qr_url:
        ticket.qr_image = qr_url
        ticket.save(update_fields=['qr_image'])

    try:
        async_task('tickets.tasks.task_send_ticket_purchase_email', ticket.pk)
    except Exception as e:
        print(f"Email queue failed: {e}")

    try:
        async_task('tickets.tasks.task_mint_nft', ticket.pk)
    except Exception as e:
        print(f"NFT queue failed: {e}")

    ticket_data              = TicketSerializer(ticket, context={'request': request}).data
    ticket_data['qr_base64'] = qr_base64
    ticket_data['nft_minting'] = True
    ticket_data['message']     = 'Ticket purchased! NFT minting on Polygon...'
    return Response(ticket_data, status=201)

# ── Transfer ticket ───────────────────────────────────────────
@api_view(['POST'])
@permission_classes([IsAuthenticated])
@ratelimit(key='user', rate='5/m', method='POST', block=False)
def transfer_ticket(request):
    if getattr(request, 'limited', False):
        return Response({'error': 'Too many transfer attempts. Please wait.'}, status=429)

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
        return Response({'error': 'Cannot transfer to yourself'}, status=status.HTTP_400_BAD_REQUEST)

    from_user = request.user

    TicketTransfer.objects.create(ticket=ticket, from_user=from_user, to_user=to_user)

    ticket.owner  = to_user
    ticket.status = 'transferred'
    ticket.save()

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

    qr_url, _ = generate_and_upload_qr(new_ticket)
    if qr_url:
        new_ticket.qr_image = qr_url
        new_ticket.save(update_fields=['qr_image'])

    # ── Queue transfer email + NFT mint ───────────────────────
    try:
        async_task('tickets.tasks.task_send_transfer_email',
                   ticket.pk, from_user.pk, to_user.pk)
    except Exception as e:
        print(f"Transfer email queue failed: {e}")

    try:
        async_task('tickets.tasks.task_mint_nft', new_ticket.pk)
    except Exception as e:
        print(f"NFT transfer queue failed (non-critical): {e}")

    return Response({
        'message':    'Ticket transferred successfully',
        'new_ticket': TicketSerializer(new_ticket, context={'request': request}).data
    })


# ── Ticket lookup helper ──────────────────────────────────────
def _find_ticket(qr_data):
    ticket_id_from_qr, _ = verify_dynamic_qr_token(qr_data)
    if ticket_id_from_qr:
        try:
            return Ticket.objects.select_related('event', 'owner').get(ticket_id=ticket_id_from_qr)
        except Ticket.DoesNotExist:
            pass
    try:
        return Ticket.objects.select_related('event', 'owner').get(qr_data=qr_data)
    except Ticket.DoesNotExist:
        pass
    try:
        return Ticket.objects.select_related('event', 'owner').get(ticket_id=qr_data.upper())
    except Ticket.DoesNotExist:
        pass
    if qr_data.startswith('MASTER-EVENTS:'):
        try:
            parts = qr_data.split(':')
            if len(parts) >= 2:
                return Ticket.objects.select_related('event', 'owner').get(id=parts[1])
        except Exception:
            pass
    return None


# ── Public scan — read-only ───────────────────────────────────
@api_view(['POST'])
@permission_classes([AllowAny])
@ratelimit(key='ip', rate='30/m', method='POST', block=False)
def public_scan_ticket(request):
    if getattr(request, 'limited', False):
        return Response({'error': 'Too many scan attempts.'}, status=429)

    qr_data = request.data.get('qr_data', '').strip()
    if not qr_data:
        return Response({'valid': False, 'reason': 'No QR data provided'}, status=400)

    ticket = _find_ticket(qr_data)
    if not ticket:
        return Response({'valid': False, 'reason': 'Ticket not found or QR expired'}, status=404)

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


# ── Verify + redeem — door staff ──────────────────────────────
@api_view(['POST'])
@permission_classes([IsAuthenticated])
@ratelimit(key='user', rate='60/m', method='POST', block=False)
def verify_ticket(request):
    if getattr(request, 'limited', False):
        return Response({'error': 'Scan rate limit exceeded.'}, status=429)

    serializer = VerifyTicketSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=400)

    data     = serializer.validated_data
    qr_data  = data['qr_data'].strip()
    event_id = data.get('event_id', 0)

    ticket = _find_ticket(qr_data)
    if not ticket:
        return Response({'valid': False, 'reason': 'Ticket not found or QR expired'}, status=404)

    if event_id and event_id != 0 and ticket.event.id != event_id:
        return Response({
            'valid':      False,
            'reason':     f'Wrong event — ticket is for {ticket.event.name}',
            'holder':     ticket.owner.get_full_name() or ticket.owner.email,
            'event_name': ticket.event.name,
        })

    if ticket.status == 'redeemed':
        return Response({
            'valid':       False,
            'reason':      'Already redeemed',
            'holder':      ticket.owner.get_full_name() or ticket.owner.email,
            'redeemed_at': ticket.redeemed_at,
            'event_name':  ticket.event.name,
        })

    if ticket.status not in ['active', 'resale']:
        return Response({
            'valid':      False,
            'reason':     f'Ticket is {ticket.status}',
            'holder':     ticket.owner.get_full_name() or ticket.owner.email,
            'event_name': ticket.event.name,
        })

    ticket.status      = 'redeemed'
    ticket.redeemed_at = timezone.now()
    ticket.save()

    # ── Queue redeemed notification ───────────────────────────
    try:
        async_task('tickets.tasks.task_send_ticket_redeemed_notification', ticket.pk)
    except Exception as e:
        print(f"Redeem notification queue failed: {e}")

    from utils.blockchain import get_polygon_explorer_url
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


# ── Generate door staff code ──────────────────────────────────
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def generate_door_code(request, event_id):
    try:
        event = Event.objects.get(pk=event_id)
    except Event.DoesNotExist:
        return Response({'error': f'Event {event_id} not found'}, status=status.HTTP_404_NOT_FOUND)

    if event.organizer != request.user:
        return Response({'error': 'You are not the organizer of this event'}, status=status.HTTP_403_FORBIDDEN)

    code      = 'DOOR-' + ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    door_code = DoorStaffCode.objects.create(event=event, code=code, created_by=request.user)

    # ── Queue door code email ─────────────────────────────────
    try:
        async_task('tickets.tasks.task_send_door_code_email',
                   event.pk, request.user.pk, code)
    except Exception as e:
        print(f"Door code email queue failed: {e}")

    return Response(DoorStaffCodeSerializer(door_code).data, status=status.HTTP_201_CREATED)


# ── Door staff login ──────────────────────────────────────────
@api_view(['POST'])
@permission_classes([AllowAny])
@ratelimit(key='ip', rate='5/m', method='POST', block=False)
def door_staff_login(request):
    if getattr(request, 'limited', False):
        return Response({'valid': False, 'error': 'Too many attempts. Please wait.'}, status=429)

    code = request.data.get('code', '').strip().upper()
    if not code:
        return Response({'valid': False, 'error': 'Code is required'}, status=400)

    try:
        door_code = DoorStaffCode.objects.select_related('event').get(
            code=code,
            is_active=True
        )
    except DoorStaffCode.DoesNotExist:
        return Response({'valid': False, 'error': 'Invalid or expired code'}, status=400)

    # ── Check 24hr expiry ─────────────────────────────────────
    if timezone.now() > door_code.created_at + timedelta(hours=24):
        door_code.is_active = False
        door_code.save(update_fields=['is_active'])
        return Response({'valid': False, 'error': 'Code has expired. Ask organizer for a new one.'}, status=400)

    # ── One-time use — deactivate after login ─────────────────
    door_code.is_active = False
    door_code.used_at   = timezone.now()
    door_code.save(update_fields=['is_active', 'used_at'])

    return Response({
        'valid':      True,
        'event_id':   door_code.event.id,
        'event_name': door_code.event.name,
        'code':       code,
    })

# ── Event tickets list ────────────────────────────────────────
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def event_tickets(request, event_id):
    try:
        event = Event.objects.get(pk=event_id, organizer=request.user)
    except Event.DoesNotExist:
        return Response({'error': 'Event not found'}, status=status.HTTP_404_NOT_FOUND)
    tickets    = Ticket.objects.filter(event=event).select_related('owner')
    serializer = TicketSerializer(tickets, many=True, context={'request': request})
    return Response(serializer.data)


# ── NFT metadata endpoint ─────────────────────────────────────
@api_view(['GET'])
@permission_classes([AllowAny])
def nft_metadata(request, ticket_id):
    try:
        ticket = Ticket.objects.select_related('event').get(ticket_id=ticket_id)
    except Ticket.DoesNotExist:
        return Response({'error': 'Not found'}, status=404)
    from utils.blockchain import build_ticket_metadata
    return Response(build_ticket_metadata(ticket))


# ── Resale listings ───────────────────────────────────────────
@api_view(['GET'])
@permission_classes([AllowAny])
def resale_listings(request):
    tickets = Ticket.objects.filter(
        status='resale'
    ).select_related('event', 'owner').order_by('-created_at')

    data = []
    for t in tickets:
        data.append({
            'ticket_id':      str(t.ticket_id),
            'resale_price':   float(t.resale_price or 0),
            'original_price': float(t.price_paid),
            'quantity':       t.quantity,
            'is_transfer':    t.is_resale,
            'nft_token_id':   t.nft_token_id,
            'event': {
                'id':       t.event.id,
                'name':     t.event.name,
                'date':     str(t.event.date),
                'time':     str(t.event.time) if t.event.time else None,
                'venue':    t.event.venue,
                'city':     getattr(t.event, 'city', 'Ghana'),
                'category': t.event.category,
                'image':    t.event.image or '',
            },
            'seller':    t.owner.first_name or 'Anonymous',
            'listed_at': t.created_at.isoformat(),
        })

    return Response(data)


# ── Buy resale ticket ─────────────────────────────────────────
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def buy_resale_ticket(request):
    from payments.models import AttendeeWallet

    ticket_id   = request.data.get('ticket_id', '')
    payment_ref = request.data.get('payment_reference', '')

    if not ticket_id:
        return Response({'error': 'ticket_id required'}, status=400)

    # ── Idempotency: if THIS user already has a ticket from this
    #    payment ref, return it instead of erroring ────────────
    existing = Ticket.objects.filter(
        payment_reference=payment_ref, owner=request.user
    ).select_related('event', 'owner').first()
    if existing:
        ticket_data = TicketSerializer(existing, context={'request': request}).data
        ticket_data['nft_minting'] = not bool(existing.nft_tx_hash)
        return Response(ticket_data, status=200)

    try:
        ticket = Ticket.objects.select_related('event', 'owner').get(
            ticket_id=ticket_id,
            status='resale',
        )
    except Ticket.DoesNotExist:
        return Response({'error': 'Resale ticket not found or already sold'}, status=404)

    if ticket.owner == request.user:
        return Response({'error': 'Cannot buy your own ticket'}, status=400)

    resale_pesewas = int((ticket.resale_price or 0) * 100)
    if resale_pesewas > 0 and not verify_paystack_payment(payment_ref, resale_pesewas):
        return Response({'error': 'Payment could not be verified'}, status=402)

    if Ticket.objects.filter(payment_reference=payment_ref).exists():
        return Response({'error': 'Payment reference already used'}, status=409)

    seller = ticket.owner

    old_ticket        = ticket
    old_ticket.status = 'transferred'
    old_ticket.save(update_fields=['status'])

    new_ticket = Ticket(
        event=ticket.event,
        owner=request.user,
        original_buyer=ticket.original_buyer,
        quantity=ticket.quantity,
        price_paid=ticket.resale_price or ticket.price_paid,
        payment_reference=payment_ref,
        status='active',
        is_resale=True,
    )
    new_ticket.save()

    qr_url, qr_base64 = generate_and_upload_qr(new_ticket)
    if qr_url:
        new_ticket.qr_image = qr_url
        new_ticket.save(update_fields=['qr_image'])

    # ── Credit ATTENDEE wallet (not organizer Wallet) ──────────
    seller_wallet, _ = AttendeeWallet.objects.get_or_create(user=seller)
    seller_amount     = (ticket.resale_price or Decimal('0')) * Decimal('0.98')
    seller_wallet.balance      += seller_amount
    seller_wallet.total_earned += seller_amount
    seller_wallet.save()

    Transaction.objects.create(
        att_wallet=seller_wallet,
        type='resale_sale',
        amount=seller_amount,
        description=f"Resale — {ticket.event.name}",
        reference=payment_ref,
        status='completed',
    )

    try:
        async_task('tickets.tasks.task_send_resale_notifications',
                   ticket.pk, seller.pk, request.user.pk, float(seller_amount))
    except Exception as e:
        print(f"Resale notification queue failed: {e}")

    try:
        async_task('tickets.tasks.task_mint_nft', new_ticket.pk)
    except Exception as e:
        print(f"Resale NFT queue failed: {e}")

    ticket_data              = TicketSerializer(new_ticket, context={'request': request}).data
    ticket_data['qr_base64'] = qr_base64
    ticket_data['nft_minting'] = True

    return Response(ticket_data, status=201)

# ── List ticket for resale ────────────────────────────────────
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def list_for_resale(request):
    ticket_id    = request.data.get('ticket_id', '')
    resale_price = request.data.get('resale_price', 0)

    if not ticket_id:
        return Response({'error': 'ticket_id required'}, status=400)

    try:
        resale_price = Decimal(str(float(resale_price)))
    except Exception:
        return Response({'error': 'Invalid price'}, status=400)

    try:
        ticket = Ticket.objects.get(
            ticket_id=ticket_id,
            owner=request.user,
            status='active',
        )
    except Ticket.DoesNotExist:
        return Response({'error': 'Ticket not found or not active'}, status=404)

    if resale_price >= ticket.price_paid:
        return Response(
            {'error': f'Resale price must be less than original price (GHS {ticket.price_paid})'},
            status=400
        )

    if resale_price < ticket.price_paid * Decimal('0.3'):
        return Response(
            {'error': f'Minimum resale price: GHS {float(ticket.price_paid) * 0.3:.2f}'},
            status=400
        )

    ticket.status       = 'resale'
    ticket.resale_price = resale_price
    ticket.save(update_fields=['status', 'resale_price'])

    # ── Queue resale listed email ─────────────────────────────
    try:
        async_task('tickets.tasks.task_send_resale_listed_email',
                   ticket.pk, request.user.pk)
    except Exception as e:
        print(f"Resale listed email queue failed: {e}")

    return Response({
        'message':      'Ticket listed for resale',
        'ticket_id':    str(ticket.ticket_id),
        'resale_price': float(resale_price),
        'status':       'resale',
    })


# ── Cancel resale listing ─────────────────────────────────────
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def cancel_resale(request):
    ticket_id = request.data.get('ticket_id', '')

    try:
        ticket = Ticket.objects.get(
            ticket_id=ticket_id,
            owner=request.user,
            status='resale',
        )
    except Ticket.DoesNotExist:
        return Response({'error': 'Resale listing not found'}, status=404)

    ticket.status       = 'active'
    ticket.resale_price = None
    ticket.save(update_fields=['status', 'resale_price'])

    return Response({'message': 'Resale listing cancelled', 'ticket_id': str(ticket.ticket_id)})