from django.db import models
from accounts.models import User
from events.models import Event
import uuid

class Ticket(models.Model):
    STATUS_CHOICES = [
        ('active',      'Active'),
        ('redeemed',    'Redeemed'),
        ('transferred', 'Transferred'),
        ('refunded',    'Refunded'),
        ('resale',      'Resale'),   # ✅ add resale status
    ]

    id              = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    ticket_id       = models.CharField(max_length=50, unique=True)
    event           = models.ForeignKey(Event, on_delete=models.CASCADE, related_name='tickets')
    owner           = models.ForeignKey(User, on_delete=models.CASCADE, related_name='tickets')
    original_buyer  = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='purchased_tickets')
    quantity        = models.IntegerField(default=1)
    price_paid      = models.DecimalField(max_digits=10, decimal_places=2)
    status          = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    qr_data         = models.CharField(max_length=500, unique=True, blank=True)
    is_resale       = models.BooleanField(default=False)
    resale_price    = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    qr_image        = models.ImageField(upload_to='qr_codes/', blank=True, null=True)
    nft_token_id    = models.BigIntegerField(null=True, blank=True)
    nft_tx_hash     = models.CharField(max_length=200, blank=True, null=True)
    nft_token_uri   = models.CharField(max_length=500, blank=True, null=True)
    owner_wallet    = models.CharField(max_length=100, blank=True, null=True)
    payment_reference = models.CharField(max_length=100, blank=True, null=True, unique=True)
    nft_mint_failed   = models.BooleanField(default=False)
    redeemed_at     = models.DateTimeField(null=True, blank=True)
    created_at      = models.DateTimeField(auto_now_add=True)


    class Meta:
        db_table = 'tickets'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.ticket_id} - {self.event.name}"

    def save(self, *args, **kwargs):
        if not self.ticket_id:
            self.ticket_id = f"TKT-{str(self.id)[:8].upper()}-GH"
        # ✅ Fix: qr_data uses ticket_id format that verify_ticket can find
        if not self.qr_data:
            self.qr_data = f"MASTER-EVENTS:{self.id}:{self.event_id}"
        super().save(*args, **kwargs)


class DoorStaffCode(models.Model):
    event      = models.ForeignKey(Event, on_delete=models.CASCADE, related_name='door_codes')
    code       = models.CharField(max_length=50, unique=True)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE)
    is_active  = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'door_staff_codes'

    def __str__(self):
        return f"{self.code} - {self.event.name}"


class TicketTransfer(models.Model):
    ticket    = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name='transfers')
    from_user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sent_transfers')
    to_user   = models.ForeignKey(User, on_delete=models.CASCADE, related_name='received_transfers')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'ticket_transfers'