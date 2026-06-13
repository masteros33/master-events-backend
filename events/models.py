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

    # ── NEW: event type + currency ─────────────────────────────
    event_type    = models.CharField(max_length=10, choices=EVENT_TYPE_CHOICES, default='paid')
    currency      = models.CharField(max_length=3, choices=CURRENCY_CHOICES, default='GHS')

    price         = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_tickets = models.IntegerField()
    tickets_sold  = models.IntegerField(default=0)
    image         = models.URLField(max_length=500, blank=True, null=True)
    sales_open    = models.BooleanField(default=True)
    is_active     = models.BooleanField(default=True)

    # ── NEW: custom subdomain slug, e.g. "tgma" → tgma.masterevents.com ──
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
        # Free events always have price = 0
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
        return f"https://{self.slug}.masterevents.com"