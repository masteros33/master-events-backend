from rest_framework import serializers
from .models import Ticket, DoorStaffCode, TicketTransfer, Registration
from events.serializers import EventSerializer
from accounts.serializers import UserSerializer
import hmac
import hashlib
import time
import qrcode
from io import BytesIO
import base64

# ── QR refreshes every 10 seconds ────────────────────────────
QR_WINDOW_SECONDS = 10


def generate_dynamic_qr_token(ticket):
    """
    HMAC-SHA256 token that changes every 10 seconds.
    Format: MASTER-EVENTS:{ticket_id}:{event_id}:{window}:{hmac}
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
    (gives grace period for slow scanners)
    Returns (ticket_id, event_id) if valid, (None, None) if invalid.
    """
    from django.conf import settings
    try:
        parts = qr_data.strip().split(':')
        if len(parts) != 5 or parts[0] != 'MASTER-EVENTS':
            return None, None

        _, ticket_id, event_id, window_str, received_token = parts
        window = int(window_str)
        current_window = int(time.time()) // QR_WINDOW_SECONDS

        secret = settings.SECRET_KEY.encode()

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


# ── TIER 2: Static, ownership-bound QR for PDF/email backup ────

def generate_static_qr_token(obj_id, event_id, owner_id):
    """
    Static, ownership-bound QR for PDF/email tickets.
    Becomes invalid the moment ownership changes OR after first use.
    Format: MASTER-EVENTS-STATIC:{obj_id}:{event_id}:{owner_hash}:{sig}
    """
    from django.conf import settings
    secret = settings.SECRET_KEY.encode()

    owner_hash = hmac.new(secret, f"{obj_id}:{owner_id}".encode(), hashlib.sha256).hexdigest()[:16]
    sig        = hmac.new(secret, f"{obj_id}:{event_id}:{owner_hash}".encode(), hashlib.sha256).hexdigest()[:16]

    return f"MASTER-EVENTS-STATIC:{obj_id}:{event_id}:{owner_hash}:{sig}"


def verify_static_qr_token(qr_data):
    """
    Verify static QR signature integrity (not ownership — that's a separate check).
    Returns (obj_id, event_id, owner_hash) if signature valid, else (None, None, None).
    """
    from django.conf import settings
    secret = settings.SECRET_KEY.encode()
    try:
        parts = qr_data.strip().split(':')
        if len(parts) != 5 or parts[0] != 'MASTER-EVENTS-STATIC':
            return None, None, None

        _, obj_id, event_id, owner_hash, sig = parts
        expected_sig = hmac.new(secret, f"{obj_id}:{event_id}:{owner_hash}".encode(), hashlib.sha256).hexdigest()[:16]

        if not hmac.compare_digest(expected_sig, sig):
            return None, None, None  # tampered

        return obj_id, int(event_id), owner_hash
    except Exception:
        return None, None, None


def compute_owner_hash(obj_id, owner_id):
    """Recompute owner_hash for a given (obj_id, owner_id) pair — used to verify
    against the CURRENT owner, catching transfers/resales."""
    from django.conf import settings
    secret = settings.SECRET_KEY.encode()
    return hmac.new(secret, f"{obj_id}:{owner_id}".encode(), hashlib.sha256).hexdigest()[:16]


def check_current_owner_hash(obj_id, current_owner_id, claimed_owner_hash):
    """Returns True if claimed_owner_hash matches the CURRENT owner —
    False means ownership changed since the PDF was issued."""
    current_hash = compute_owner_hash(obj_id, current_owner_id)
    return hmac.compare_digest(current_hash, claimed_owner_hash)


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
            'dynamic_qr',
            'is_resale', 'resale_price',
            'redeemed_at', 'created_at',
            'nft_tx_hash', 'nft_token_id', 'nft_token_uri',
            'pdf_redemption_used',
        ]

    def get_qr_image_url(self, obj):
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
        This is what the scanner reads — changes every 10 seconds.
        """
        if obj.status not in ['active', 'resale']:
            return None
        try:
            qr_content = generate_dynamic_qr_token(obj)
            return generate_qr_base64(qr_content)
        except Exception as e:
            print(f"Dynamic QR generation error: {e}")
            return None


class RegistrationSerializer(serializers.ModelSerializer):
    event        = EventSerializer(read_only=True)
    attendee     = UserSerializer(read_only=True)
    qr_image_url = serializers.SerializerMethodField()

    class Meta:
        model = Registration
        fields = [
            'id', 'registration_id', 'event', 'attendee', 'quantity',
            'status', 'qr_data', 'qr_image', 'qr_image_url',
            'pdf_redemption_used', 'redeemed_at', 'created_at',
        ]

    def get_qr_image_url(self, obj):
        if not obj.qr_image:
            return None
        url = str(obj.qr_image)
        if url.startswith('http'):
            return url
        request = self.context.get('request')
        if request:
            return request.build_absolute_uri(obj.qr_image.url)
        return f"https://master-events-backend.onrender.com{obj.qr_image.url}"


class PurchaseSerializer(serializers.Serializer):
    event_id          = serializers.IntegerField()
    quantity          = serializers.IntegerField(min_value=1, max_value=10)
    payment_reference = serializers.CharField()


class RegisterFreeEventSerializer(serializers.Serializer):
    event_id = serializers.IntegerField()
    quantity = serializers.IntegerField(min_value=1, max_value=10, default=1)


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