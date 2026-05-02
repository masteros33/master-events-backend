from rest_framework import serializers
from .models import Ticket, DoorStaffCode, TicketTransfer
from events.serializers import EventSerializer
from accounts.serializers import UserSerializer
import hmac
import hashlib
import time
import qrcode
from io import BytesIO
import base64

# ── QR refreshes every 30 seconds ────────────────────────────
QR_WINDOW_SECONDS = 10


def generate_dynamic_qr_token(ticket):
    """
    HMAC-SHA256 token that changes every 30 seconds.
    Format: MASTER-EVENTS:{ticket_id}:{event_id}:{window}:{hmac}
    Window = unix timestamp // 30  (changes every 30s)
    """
    from django.conf import settings
    secret = settings.SECRET_KEY.encode()
    window = int(time.time()) // QR_WINDOW_SECONDS
    message = f"{ticket.ticket_id}:{ticket.event_id}:{window}".encode()
    token = hmac.new(secret, message, hashlib.sha256).hexdigest()[:16]
    return f"MASTER-EVENTS:{ticket.ticket_id}:{ticket.event_id}:{window}:{token}"


def verify_dynamic_qr_token(qr_data):
    """
    Verify HMAC token — accepts current window AND previous window
    (gives 30s grace period for slow scanners)
    Returns ticket_id if valid, None if invalid.
    """
    from django.conf import settings
    try:
        parts = qr_data.strip().split(':')
        # Format: MASTER-EVENTS:{ticket_id}:{event_id}:{window}:{hmac}
        if len(parts) != 5 or parts[0] != 'MASTER-EVENTS':
            return None, None

        _, ticket_id, event_id, window_str, received_token = parts
        window = int(window_str)
        current_window = int(time.time()) // QR_WINDOW_SECONDS

        secret = settings.SECRET_KEY.encode()

        # Check current window and previous window (grace period)
        for w in [current_window, current_window - 1]:
            message = f"{ticket_id}:{event_id}:{w}".encode()
            expected = hmac.new(secret, message, hashlib.sha256).hexdigest()[:16]
            if hmac.compare_digest(expected, received_token):
                if abs(window - current_window) <= 1:
                    return ticket_id, int(event_id)

        return None, None
    except Exception as e:
        print(f"QR verify error: {e}")
        return None, None


def generate_qr_base64(qr_content):
    """Generate QR code as base64 string for frontend display"""
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
    return base64.b64encode(buffer.getvalue()).decode()


class TicketSerializer(serializers.ModelSerializer):
    event        = EventSerializer(read_only=True)
    owner        = UserSerializer(read_only=True)
    qr_image_url = serializers.SerializerMethodField()
    dynamic_qr   = serializers.SerializerMethodField()

    class Meta:
        model = Ticket
        fields = [
            'id', 'ticket_id', 'event', 'owner', 'quantity',
            'price_paid', 'status', 'qr_data', 'qr_image',
            'qr_image_url',
            # ✅ dynamic_qr — base64 QR that changes every 30s
            'dynamic_qr',
            'is_resale', 'resale_price',
            'redeemed_at', 'created_at',
            'nft_tx_hash', 'nft_token_id', 'nft_token_uri',
        ]

    def get_qr_image_url(self, obj):
        """Return Cloudinary URL or absolute backend URL"""
        if not obj.qr_image:
            return None
        url = str(obj.qr_image)
        if url.startswith('http'):
            return url
        request = self.context.get('request')
        if request:
            return request.build_absolute_uri(obj.qr_image.url)
        return f"https://master-events-backend.onrender.com{obj.qr_image.url}"

    def get_dynamic_qr(self, obj):
        """
        Generate a fresh HMAC QR every request.
        This is what the scanner reads — changes every 30 seconds.
        Static QR screenshots become invalid after 30s.
        """
        if obj.status not in ['active', 'resale']:
            return None
        try:
            qr_content = generate_dynamic_qr_token(obj)
            return generate_qr_base64(qr_content)
        except Exception as e:
            print(f"Dynamic QR generation error: {e}")
            return None


class PurchaseSerializer(serializers.Serializer):
    event_id          = serializers.IntegerField()
    quantity          = serializers.IntegerField(min_value=1, max_value=10)
    payment_reference = serializers.CharField()


class TransferSerializer(serializers.Serializer):
    ticket_id = serializers.CharField()
    to_email  = serializers.EmailField()

class VerifyTicketSerializer(serializers.Serializer):
    qr_data  = serializers.CharField()
    event_id = serializers.IntegerField(required=False, default=0)

class DoorStaffCodeSerializer(serializers.ModelSerializer):
    event_name = serializers.CharField(source='event.name', read_only=True)

    class Meta:
        model  = DoorStaffCode
        fields = ['id', 'code', 'event', 'event_name', 'is_active', 'created_at']