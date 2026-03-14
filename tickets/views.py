from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from django.utils import timezone
from django.conf import settings
from django.core.files.base import ContentFile
from .models import Ticket, DoorStaffCode, TicketTransfer
from .serializers import TicketSerializer, PurchaseSerializer, TransferSerializer, VerifyTicketSerializer, DoorStaffCodeSerializer
from events.models import Event
from accounts.models import User
from payments.models import Wallet, Transaction
import random
import string
import uuid
import qrcode
import qrcode.image.svg
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

    total = float(event.price) * data['quantity']

    # Create ticket first to get UUID
    ticket = Ticket(
        event=event,
        owner=request.user,
        original_buyer=request.user,
        quantity=data['quantity'],
        price_paid=total,
        status='active',
    )
    ticket.save()

    # Generate QR code as base64
    qr_content = f"MASTER-EVENTS:{ticket.id}:{event.id}:{request.user.id}"
    ticket.qr_data = qr_content

    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(qr_content)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buffer = BytesIO()
    img.save(buffer, format='PNG')
    qr_base64 = base64.b64encode(buffer.getvalue()).decode()

    # Save QR image to ticket
    ticket.qr_image = ContentFile(
        buffer.getvalue(),
        name=f"qr_{ticket.ticket_id}.png"
    )
    ticket.save()

    event.tickets_sold += data['quantity']
    event.save()

    # Split payment — 95% organizer, 5% platform
    organizer_wallet, _ = Wallet.objects.get_or_create(user=event.organizer)
    organizer_amount = total * 0.95

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

    ticket_data = TicketSerializer(ticket).data
    ticket_data['qr_base64'] = qr_base64

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

    return Response({'message': 'Ticket transferred successfully', 'new_ticket': TicketSerializer(new_ticket).data})

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def verify_ticket(request):
    serializer = VerifyTicketSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    data = serializer.validated_data
    try:
        ticket = Ticket.objects.get(qr_data=data['qr_data'])
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
    })

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def generate_door_code(request, event_id):
    try:
        event = Event.objects.get(pk=event_id, organizer=request.user)
    except Event.DoesNotExist:
        return Response({'error': 'Event not found'}, status=status.HTTP_404_NOT_FOUND)

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