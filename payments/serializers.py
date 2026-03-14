from rest_framework import serializers
from .models import Wallet, Transaction

class TransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Transaction
        fields = ['id', 'type', 'amount', 'description', 'reference', 'status', 'created_at']

class WalletSerializer(serializers.ModelSerializer):
    transactions = TransactionSerializer(many=True, read_only=True)
    fees_paid = serializers.SerializerMethodField()

    class Meta:
        model = Wallet
        fields = ['id', 'balance', 'total_earned', 'total_withdrawn', 'fees_paid', 'transactions', 'created_at']

    def get_fees_paid(self, obj):
        return float(obj.total_earned) * 0.05 / 0.95