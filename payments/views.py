from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from django.conf import settings
from .models import Wallet, Transaction
from .serializers import WalletSerializer, TransactionSerializer
from utils.emails import notify_withdrawal
import uuid

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def wallet_detail(request):
    wallet, _ = Wallet.objects.get_or_create(user=request.user)
    serializer = WalletSerializer(wallet)
    return Response(serializer.data)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def withdraw(request):
    amount = float(request.data.get('amount', 0))
    method = request.data.get('method', 'momo')
    account = request.data.get('account', '')

    if amount < 10:
        return Response({'error': 'Minimum withdrawal is Ghc 10'}, status=status.HTTP_400_BAD_REQUEST)

    if not account:
        return Response({'error': 'Account number is required'}, status=status.HTTP_400_BAD_REQUEST)

    wallet, _ = Wallet.objects.get_or_create(user=request.user)

    if float(wallet.balance) < amount:
        return Response({'error': 'Insufficient balance'}, status=status.HTTP_400_BAD_REQUEST)

    reference = f"WD-{str(uuid.uuid4())[:8].upper()}"

    wallet.balance -= amount
    wallet.total_withdrawn += amount
    wallet.save()

    Transaction.objects.create(
        wallet=wallet,
        type='withdrawal',
        amount=amount,
        description=f"Withdrawal via {'MoMo' if method == 'momo' else 'Bank'}",
        reference=reference,
        status='completed',
    )

    # Send notification + email
    notify_withdrawal(wallet, amount, method, reference)

    return Response({
        'message': 'Withdrawal initiated successfully',
        'amount': amount,
        'reference': reference,
        'method': method,
        'account': account,
        'new_balance': float(wallet.balance),
    })

@api_view(['POST'])
@permission_classes([AllowAny])
def paystack_webhook(request):
    payload = request.data
    event = payload.get('event')
    if event == 'charge.success':
        reference = payload['data']['reference']
        amount = payload['data']['amount'] / 100
    return Response({'status': 'ok'})

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def transaction_history(request):
    wallet, _ = Wallet.objects.get_or_create(user=request.user)
    transactions = wallet.transactions.all()[:20]
    serializer = TransactionSerializer(transactions, many=True)
    return Response(serializer.data)