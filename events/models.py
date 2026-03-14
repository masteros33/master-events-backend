from django.db import models
from accounts.models import User

class Event(models.Model):
    CATEGORY_CHOICES = [
        ('music', 'Music'),
        ('tech', 'Tech'),
        ('food', 'Food & Drink'),
        ('arts', 'Arts & Culture'),
        ('sports', 'Sports'),
        ('business', 'Business'),
        ('other', 'Other'),
    ]

    organizer = models.ForeignKey(User, on_delete=models.CASCADE, related_name='events')
    name = models.CharField(max_length=200)
    description = models.TextField()
    category = models.CharField(max_length=50, choices=CATEGORY_CHOICES, default='other')
    venue = models.CharField(max_length=200)
    city = models.CharField(max_length=100, default='Accra')
    date = models.DateField()
    time = models.TimeField()
    price = models.DecimalField(max_digits=10, decimal_places=2)
    total_tickets = models.IntegerField()
    tickets_sold = models.IntegerField(default=0)
    image = models.ImageField(upload_to='events/', blank=True, null=True)
    sales_open = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'events'
        ordering = ['-created_at']

    def __str__(self):
        return self.name

    @property
    def tickets_remaining(self):
        return self.total_tickets - self.tickets_sold

    @property
    def is_sold_out(self):
        return self.tickets_sold >= self.total_tickets

    @property
    def revenue(self):
        return float(self.price) * self.tickets_sold * 0.95