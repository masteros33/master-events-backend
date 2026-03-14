from django.contrib import admin
from .models import Event

@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ['name', 'organizer', 'city', 'date', 'price', 'tickets_sold', 'total_tickets', 'sales_open']
    list_filter = ['city', 'category', 'sales_open', 'is_active']
    search_fields = ['name', 'organizer__email']
    ordering = ['-created_at']