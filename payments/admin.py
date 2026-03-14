from django.contrib import admin
from .models import Wallet, Transaction

@admin.register(Wallet)
class WalletAdmin(admin.ModelAdmin):
    list_display = ['user', 'balance', 'total_earned', 'total_withdrawn', 'updated_at']
    search_fields = ['user__email']

@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ['reference', 'wallet', 'type', 'amount', 'status', 'created_at']
    list_filter = ['type', 'status']
    search_fields = ['reference', 'wallet__user__email']