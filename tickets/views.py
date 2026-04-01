from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from django.utils import timezone
from django.core.files.base import ContentFile
from .models import Ticket, DoorStaffCode, TicketTransfer
from .serializers import TicketSerializer, PurchaseSerializer, TransferSerializer, VerifyTicketSerializer, DoorStaffCodeSerializer
from events.models import Event
from accounts.models import User
from payments.models import Wallet, Transaction
from utils.emails import notify_ticket_purchase, notify_ticket_transfer
from utils.blockchain import mint_ticket_nft, get_polygon_explorer_url
from decimal import Decimal
import random
import string
import qrcode
from io import BytesIO
import base64

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def my_tickets(request):
    tickets = Ticket.objects.filter(owner=request.user).exclude(status='transferred')
    serializer = TicketSerializer(tickets, many=True)
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

    qr_content = f"MASTER-EVENTS:{ticket.id}:{event.id}:{request.user.id}"
    ticket.qr_data = qr_content

    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(qr_content)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buffer = BytesIO()
    img.save(buffer, format='PNG')
    qr_base64 = base64.b64encode(buffer.getvalue()).decode()

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

    # Send notification + email
    notify_ticket_purchase(ticket)

    # Prepare response
    ticket_data = TicketSerializer(ticket).data
    ticket_data['qr_base64'] = qr_base64

# Mint NFT async — doesn't block API response
    try:
        from utils.blockchain import mint_ticket_nft_async
        owner_wallet = getattr(request.user, 'wallet_address', None)

        def on_mint_success(nft_result):
            try:
                from tickets.models import Ticket as TicketModel
                t = TicketModel.objects.get(pk=ticket.pk)
                t.nft_token_id = nft_result['token_id']
                t.nft_tx_hash = nft_result['tx_hash']
                t.nft_token_uri = nft_result['token_uri']
                t.save()
                print(f"✅ Ticket {t.ticket_id} NFT saved: token_id={nft_result['token_id']}")
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
    ticket.owner = to_user
    ticket.status = 'transferred'
    ticket.save()

    new_ticket = Ticket.objects.create(
        event=ticket.event,
        owner=to_user,
        original_buyer=ticket.original_buyer,
        quantity=ticket.quantity,
        price_paid=ticket.price_paid,
        status='active',
        is_resale=True,
    )

    # Send notification + email
    notify_ticket_transfer(ticket, request.user, to_user)

    # Transfer NFT on blockchain
    try:
        if ticket.nft_token_id and to_user.wallet_address:
            from utils.blockchain import transfer_ticket_nft
            transfer_ticket_nft(
                ticket.nft_token_id,
                request.user.wallet_address,
                to_user.wallet_address
            )
    except Exception as e:
        print(f"NFT transfer failed (non-critical): {e}")

    return Response({'message': 'Ticket transferred successfully', 'new_ticket': TicketSerializer(new_ticket).data})

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def verify_ticket(request):
    serializer = VerifyTicketSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    data = serializer.validated_data
    qr_data = data['qr_data'].strip()

    ticket = None
    try:
        ticket = Ticket.objects.get(qr_data=qr_data)
    except Ticket.DoesNotExist:
        try:
            ticket = Ticket.objects.get(ticket_id=qr_data.upper())
        except Ticket.DoesNotExist:
            return Response({'valid': False, 'reason': 'Ticket not found'}, status=status.HTTP_404_NOT_FOUND)

    if ticket.event.id != data['event_id']:
        return Response({'valid': False, 'reason': 'Wrong event', 'holder': ticket.owner.full_name})

    if ticket.status == 'redeemed':
        return Response({'valid': False, 'reason': 'Already redeemed', 'holder': ticket.owner.full_name})

    if ticket.status != 'active':
        return Response({'valid': False, 'reason': f'Ticket is {ticket.status}', 'holder': ticket.owner.full_name})

    ticket.status = 'redeemed'
    ticket.redeemed_at = timezone.now()
    ticket.save()

    return Response({
        'valid': True,
        'holder': ticket.owner.full_name,
        'ticket_id': ticket.ticket_id,
        'event': ticket.event.name,
        'quantity': ticket.quantity,
        'is_transfer': ticket.is_resale,
        'nft_token_id': ticket.nft_token_id,
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
        'valid': True,
        'event_id': door_code.event.id,
        'event_name': door_code.event.name,
        'code': door_code.code,
    })

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def event_tickets(request, event_id):
    try:
        event = Event.objects.get(pk=event_id, organizer=request.user)
    except Event.DoesNotExist:
        return Response({'error': 'Event not found'}, status=status.HTTP_404_NOT_FOUND)
    tickets = Ticket.objects.filter(event=event)
    serializer = TicketSerializer(tickets, many=True)
    return Response(serializer.data)