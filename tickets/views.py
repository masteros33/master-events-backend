from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from django.utils import timezone
from .models import Ticket, DoorStaffCode, TicketTransfer
from .serializers import TicketSerializer, PurchaseSerializer, TransferSerializer, VerifyTicketSerializer, DoorStaffCodeSerializer, verify_dynamic_qr_token
from events.models import Event
from accounts.models import User
from payments.models import Wallet, Transaction
from utils.emails import notify_ticket_purchase, notify_ticket_transfer
from utils.blockchain import mint_ticket_nft_async, get_polygon_explorer_url
from decimal import Decimal
import random
import string
import qrcode
from io import BytesIO
import base64
import cloudinary.uploader


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
    try:
        event = Event.objects.get(pk=data['event_id'], is_active=True, sales_open=True)
    except Event.DoesNotExist:
        return Response({'error': 'Event not found or sales closed'}, status=status.HTTP_404_NOT_FOUND)

    if event.tickets_remaining < data['quantity']:
        return Response({'error': 'Not enough tickets available'}, status=status.HTTP_400_BAD_REQUEST)

    total = Decimal(str(float(event.price) * data['quantity']))

    ticket = Ticket(
        event=event,
        owner=request.user,
        original_buyer=request.user,
        quantity=data['quantity'],
        price_paid=total,
        status='active',
    )
    ticket.save()

    qr_content = ticket.qr_data
    qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_H, box_size=10, border=4)
    qr.add_data(qr_content)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buffer = BytesIO()
    img.save(buffer, format='PNG')
    buffer.seek(0)
    qr_base64 = base64.b64encode(buffer.getvalue()).decode()

    try:
        buffer.seek(0)
        cloudinary_result = cloudinary.uploader.upload(
            buffer,
            folder="master_events/qr_codes",
            public_id=f"qr_{ticket.ticket_id}",
            resource_type="image",
            overwrite=True,
        )
        ticket.qr_image = cloudinary_result['secure_url']
        print(f"✅ QR uploaded to Cloudinary: {cloudinary_result['secure_url']}")
    except Exception as e:
        print(f"⚠️ QR Cloudinary upload failed: {e}")
        from django.core.files.base import ContentFile
        buffer.seek(0)
        ticket.qr_image = ContentFile(buffer.getvalue(), name=f"qr_{ticket.ticket_id}.png")

    ticket.save()

    event.tickets_sold += data['quantity']
    event.save()

    organizer_wallet, _ = Wallet.objects.get_or_create(user=event.organizer)
    organizer_amount = total * Decimal('0.95')
    organizer_wallet.balance += organizer_amount
    organizer_wallet.total_earned += organizer_amount
    organizer_wallet.save()

    Transaction.objects.create(
        wallet=organizer_wallet,
        type='sale',
        amount=organizer_amount,
        description=f"{data['quantity']}x {event.name}",
        reference=data['payment_reference'],
        status='completed',
    )

    try:
        notify_ticket_purchase(ticket)
    except Exception as e:
        print(f"Email notification failed: {e}")

    ticket_data = TicketSerializer(ticket, context={'request': request}).data
    ticket_data['qr_base64'] = qr_base64

    try:
        owner_wallet = getattr(request.user, 'wallet_address', None)

        def on_mint_success(nft_result):
            try:
                from tickets.models import Ticket as TicketModel
                t = TicketModel.objects.get(pk=ticket.pk)
                t.nft_token_id  = nft_result['token_id']
                t.nft_tx_hash   = nft_result['tx_hash']
                t.nft_token_uri = nft_result['token_uri']
                t.save()
                print(f"✅ NFT saved for ticket {t.ticket_id}: token={nft_result['token_id']}")
            except Exception as e:
                print(f"Error saving NFT result: {e}")

        mint_ticket_nft_async(ticket, owner_wallet, callback=on_mint_success)
        ticket_data['nft_minting'] = True
        ticket_data['message'] = 'Ticket purchased! NFT minting on Polygon...'
    except Exception as e:
        print(f"NFT mint failed (non-critical): {e}")

    return Response(ticket_data, status=status.HTTP_201_CREATED)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def transfer_ticket(request):
    serializer = TransferSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    data = serializer.validated_data
    try:
        ticket = Ticket.objects.get(ticket_id=data['ticket_id'], owner=request.user, status='active')
    except Ticket.DoesNotExist:
        return Response({'error': 'Ticket not found'}, status=status.HTTP_404_NOT_FOUND)

    try:
        to_user = User.objects.get(email=data['to_email'])
    except User.DoesNotExist:
        return Response({'error': 'User not found with that email'}, status=status.HTTP_404_NOT_FOUND)

    if to_user == request.user:
        return Response({'error': 'Cannot transfer to yourself'}, status=status.HTTP_400_BAD_REQUEST)

    TicketTransfer.objects.create(ticket=ticket, from_user=request.user, to_user=to_user)

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

    qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_H, box_size=10, border=4)
    qr.add_data(new_ticket.qr_data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buffer = BytesIO()
    img.save(buffer, format='PNG')
    buffer.seek(0)

    try:
        cloudinary_result = cloudinary.uploader.upload(
            buffer,
            folder="master_events/qr_codes",
            public_id=f"qr_{new_ticket.ticket_id}",
            resource_type="image",
            overwrite=True,
        )
        new_ticket.qr_image = cloudinary_result['secure_url']
        new_ticket.save()
    except Exception as e:
        print(f"QR upload for transfer failed: {e}")

    try:
        notify_ticket_transfer(ticket, request.user, to_user)
    except Exception as e:
        print(f"Transfer email failed: {e}")

    try:
        if ticket.nft_token_id and to_user.wallet_address:
            from utils.blockchain import transfer_ticket_nft
            transfer_ticket_nft(ticket.nft_token_id, request.user.wallet_address, to_user.wallet_address)
    except Exception as e:
        print(f"NFT transfer failed (non-critical): {e}")

    return Response({
        'message': 'Ticket transferred successfully',
        'new_ticket': TicketSerializer(new_ticket, context={'request': request}).data
    })


def _find_ticket(qr_data):
    """Shared ticket lookup used by both verify and public scan."""
    ticket = None

    # Strategy 1: Dynamic HMAC QR
    ticket_id_from_qr, _ = verify_dynamic_qr_token(qr_data)
    if ticket_id_from_qr:
        try:
            ticket = Ticket.objects.select_related('event', 'owner').get(ticket_id=ticket_id_from_qr)
            return ticket
        except Ticket.DoesNotExist:
            pass

    # Strategy 2: Static qr_data
    try:
        return Ticket.objects.select_related('event', 'owner').get(qr_data=qr_data)
    except Ticket.DoesNotExist:
        pass

    # Strategy 3: Direct ticket_id
    try:
        return Ticket.objects.select_related('event', 'owner').get(ticket_id=qr_data.upper())
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
    Public QR scan — anyone with a phone camera can scan.
    Returns ticket owner info WITHOUT redeeming the ticket.
    Read-only. Safe to expose publicly.
    """
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
        'event_city':   ticket.event.city,
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

    data     = serializer.validated_data
    qr_data  = data['qr_data'].strip()
    event_id = data['event_id']

    ticket = _find_ticket(qr_data)

    if not ticket:
        return Response({'valid': False, 'reason': 'Ticket not found or QR expired'}, status=404)

    # Event check
    if event_id and event_id != 0 and ticket.event.id != event_id:
        return Response({
            'valid':  False,
            'reason': f'Wrong event — ticket is for {ticket.event.name}',
            'holder': ticket.owner.get_full_name() or ticket.owner.email,
        })

    # Status check
    if ticket.status == 'redeemed':
        return Response({
            'valid':       False,
            'reason':      'Already redeemed',
            'holder':      ticket.owner.get_full_name() or ticket.owner.email,
            'redeemed_at': ticket.redeemed_at,
        })

    if ticket.status not in ['active', 'resale']:
        return Response({
            'valid':  False,
            'reason': f'Ticket is {ticket.status}',
            'holder': ticket.owner.get_full_name() or ticket.owner.email,
        })

    # ✅ Admit — mark as redeemed
    ticket.status      = 'redeemed'
    ticket.redeemed_at = timezone.now()
    ticket.save()

    return Response({
        'valid':          True,
        'holder':         ticket.owner.get_full_name() or ticket.owner.email,
        'holder_email':   ticket.owner.email,
        'ticket_id':      str(ticket.ticket_id),
        'event':          ticket.event.name,
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
        return Response({'error': f'Event {event_id} not found'}, status=status.HTTP_404_NOT_FOUND)

    if event.organizer != request.user:
        return Response({'error': 'You are not the organizer.'}, status=status.HTTP_403_FORBIDDEN)

    code = 'DOOR-' + ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    door_code = DoorStaffCode.objects.create(event=event, code=code, created_by=request.user)
    return Response(DoorStaffCodeSerializer(door_code).data, status=status.HTTP_201_CREATED)


@api_view(['POST'])
@permission_classes([AllowAny])
def door_staff_login(request):
    code = request.data.get('code', '').upper()
    try:
        door_code = DoorStaffCode.objects.get(code=code, is_active=True)
    except DoorStaffCode.DoesNotExist:
        return Response({'error': 'Invalid or expired door code'}, status=status.HTTP_400_BAD_REQUEST)

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