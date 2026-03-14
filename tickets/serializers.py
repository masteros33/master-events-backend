from rest_framework import serializers
from .models import Ticket, DoorStaffCode, TicketTransfer
from events.serializers import EventSerializer
from accounts.serializers import UserSerializer

class TicketSerializer(serializers.ModelSerializer):
    event = EventSerializer(read_only=True)
    owner = UserSerializer(read_only=True)

    class Meta:
        model = Ticket
        fields = [
            'id', 'ticket_id', 'event', 'owner', 'quantity',
            'price_paid', 'status', 'qr_data', 'qr_image', 'is_resale',
            'resale_price', 'redeemed_at', 'created_at'
        ]

class PurchaseSerializer(serializers.Serializer):
    event_id = serializers.IntegerField()
    quantity = serializers.IntegerField(min_value=1, max_value=10)
    payment_reference = serializers.CharField()

class TransferSerializer(serializers.Serializer):
    ticket_id = serializers.CharField()
    to_email = serializers.EmailField()

class VerifyTicketSerializer(serializers.Serializer):
    qr_data = serializers.CharField()
    event_id = serializers.IntegerField()

class DoorStaffCodeSerializer(serializers.ModelSerializer):
    event_name = serializers.CharField(source='event.name', read_only=True)

    class Meta:
        model = DoorStaffCode
        fields = ['id', 'code', 'event', 'event_name', 'is_active', 'created_at']