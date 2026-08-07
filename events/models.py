from django.db import models
from django.utils.text import slugify
from accounts.models import User

class Event(models.Model):
    CATEGORY_CHOICES = [
        ('music',    'Music'),
        ('tech',     'Tech'),
        ('food',     'Food & Drink'),
        ('arts',     'Arts & Culture'),
        ('sports',   'Sports'),
        ('business', 'Business'),
        ('other',    'Other'),
    ]

    EVENT_TYPE_CHOICES = [
        ('paid', 'Paid'),
        ('free', 'Free'),
    ]

    CURRENCY_CHOICES = [
        ('GHS', 'Ghana Cedi'),
        ('USD', 'US Dollar'),
        ('EUR', 'Euro'),
        ('GBP', 'British Pound'),
        ('NGN', 'Nigerian Naira'),
    ]

    organizer     = models.ForeignKey(User, on_delete=models.CASCADE, related_name='events')
    name          = models.CharField(max_length=200)
    description   = models.TextField(blank=True, default='')
    category      = models.CharField(max_length=50, choices=CATEGORY_CHOICES, default='other')
    venue         = models.CharField(max_length=200)
    city          = models.CharField(max_length=100, default='Accra')
    country       = models.CharField(max_length=100, default='Ghana')
    date          = models.DateField()
    time          = models.TimeField()

    event_type    = models.CharField(max_length=10, choices=EVENT_TYPE_CHOICES, default='paid')
    currency      = models.CharField(max_length=3, choices=CURRENCY_CHOICES, default='GHS')

    price         = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_tickets = models.IntegerField()
    tickets_sold  = models.IntegerField(default=0)
    image         = models.URLField(max_length=500, blank=True, null=True)
    sales_open    = models.BooleanField(default=True)
    is_active     = models.BooleanField(default=True)

    # ── NEW: admin approval gate. Every event starts unapproved and is
    # invisible on public discovery (event_list) until a super admin
    # reviews and approves it. This is the core fix against the scam
    # scenario — an organizer creating a fake event, selling tickets,
    # and disappearing before the event date. Organizers still see
    # their own pending events immediately via my_events (unfiltered),
    # so the create flow doesn't feel broken — they just see a
    # "Pending Review" state instead of "Live". ──
    is_approved   = models.BooleanField(default=False)

    slug          = models.SlugField(max_length=60, unique=True, blank=True)

    created_at    = models.DateTimeField(auto_now_add=True)
    updated_at    = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'events'
        ordering = ['-created_at']

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.name)[:40]
            slug = base
            i = 1
            while Event.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base}-{i}"
                i += 1
            self.slug = slug
        if self.event_type == 'free':
            self.price = 0
        super().save(*args, **kwargs)

    @property
    def tickets_remaining(self):
        return self.total_tickets - self.tickets_sold

    @property
    def is_sold_out(self):
        return self.tickets_sold >= self.total_tickets

    @property
    def revenue(self):
        return float(self.price) * self.tickets_sold * 0.95

    @property
    def event_url(self):
        return f"https://masterevents.events/events/{self.slug}"


class TicketTier(models.Model):
    """
    Optional per-event ticket tiers (Regular/VIP/VVIP/custom).
    An event with no tiers still works exactly as before, using its
    own price/total_tickets — tiers are purely additive, never required.
    """
    event    = models.ForeignKey(Event, on_delete=models.CASCADE, related_name='tiers')
    name     = models.CharField(max_length=100)
    price    = models.DecimalField(max_digits=10, decimal_places=2)
    capacity = models.IntegerField()
    sold     = models.IntegerField(default=0)
    order    = models.IntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'ticket_tiers'
        ordering = ['order', 'price']

    def __str__(self):
        return f"{self.name} — {self.event.name}"

    @property
    def remaining(self):
        return self.capacity - self.sold

    @property
    def is_sold_out(self):
        return self.sold >= self.capacity