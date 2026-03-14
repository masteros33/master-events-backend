from django.contrib import admin
from .models import Ticket, DoorStaffCode, TicketTransfer

@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    list_display = ['ticket_id', 'event', 'owner', 'status', 'price_paid', 'created_at']
    list_filter = ['status', 'is_resale']
    search_fields = ['ticket_id', 'owner__email', 'event__name']

@admin.register(DoorStaffCode)
class DoorStaffCodeAdmin(admin.ModelAdmin):
    list_display = ['code', 'event', 'created_by', 'is_active', 'created_at']
    list_filter = ['is_active']

@admin.register(TicketTransfer)
class TicketTransferAdmin(admin.ModelAdmin):
    list_display = ['ticket', 'from_user', 'to_user', 'created_at']