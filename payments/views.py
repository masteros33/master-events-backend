from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from .models import Wallet, Transaction
from .serializers import WalletSerializer, TransactionSerializer
from utils.emails import notify_withdrawal
from decimal import Decimal
import uuid
import requests
import hmac
import hashlib
import json


# ── Paystack helpers ──────────────────────────────────────────
def get_paystack_headers():
    return {
        "Authorization": f"Bearer {getattr(settings, 'PAYSTACK_SECRET_KEY', '')}",
        "Content-Type":  "application/json",
    }


def resolve_momo_recipient(phone, name):
    """
    Create a Paystack transfer recipient for MoMo.
    Returns recipient_code or None.
    Works in test mode — Paystack simulates this.
    """
    secret_key = getattr(settings, 'PAYSTACK_SECRET_KEY', '')
    if not secret_key:
        return None
    try:
        resp = requests.post(
            "https://api.paystack.co/transferrecipient",
            headers=get_paystack_headers(),
            json={
                "type":           "mobile_money",
                "name":           name or "Master Events Organizer",
                "account_number": phone,
                "bank_code":      "MTN",   # MTN MoMo Ghana
                "currency":       "GHS",
            },
            timeout=15,
        )
        data = resp.json()
        if data.get("status") and data.get("data", {}).get("recipient_code"):
            return data["data"]["recipient_code"]
        print(f"Recipient create failed: {data}")
        return None
    except Exception as e:
        print(f"resolve_momo_recipient error: {e}")
        return None


def initiate_paystack_transfer(amount_ghs, recipient_code, reference, reason):
    """
    Initiate a Paystack transfer (payout).
    amount_ghs is in Ghana Cedis — we convert to pesewas for Paystack.
    In test mode Paystack simulates this and marks it successful.
    Returns (success: bool, transfer_code: str|None, message: str)
    """
    secret_key = getattr(settings, 'PAYSTACK_SECRET_KEY', '')
    if not secret_key:
        return False, None, "Paystack not configured"
    try:
        resp = requests.post(
            "https://api.paystack.co/transfer",
            headers=get_paystack_headers(),
            json={
                "source":    "balance",
                "amount":    int(Decimal(str(amount_ghs)) * 100),  # pesewas
                "recipient": recipient_code,
                "reason":    reason,
                "reference": reference,
                "currency":  "GHS",
            },
            timeout=15,
        )
        data = resp.json()
        print(f"Paystack transfer response: {data}")

        if data.get("status"):
            transfer_code = data.get("data", {}).get("transfer_code")
            tx_status     = data.get("data", {}).get("status", "")
            # In test mode status is "success" immediately
            # In live mode it may be "pending" until webhook fires
            if tx_status in ["success", "pending", "otp"]:
                return True, transfer_code, tx_status
        return False, None, data.get("message", "Transfer failed")
    except Exception as e:
        print(f"initiate_paystack_transfer error: {e}")
        return False, None, str(e)


# ── Wallet detail ─────────────────────────────────────────────
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def wallet_detail(request):
    wallet, _ = Wallet.objects.get_or_create(user=request.user)
    serializer = WalletSerializer(wallet)
    return Response(serializer.data)


# ── Withdraw — full Paystack transfer flow ────────────────────
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def withdraw(request):
    amount_raw = request.data.get('amount', 0)
    method     = request.data.get('method', 'momo')
    account    = request.data.get('account', '').strip()

    # ── Validate inputs ───────────────────────────────────────
    try:
        amount = Decimal(str(float(amount_raw)))
    except Exception:
        return Response({'error': 'Invalid amount'}, status=400)

    if amount < 10:
        return Response({'error': 'Minimum withdrawal is Ghc 10'}, status=400)

    if not account:
        return Response({'error': 'Account number is required'}, status=400)

    wallet, _ = Wallet.objects.get_or_create(user=request.user)

    if wallet.balance < amount:
        return Response({'error': 'Insufficient balance'}, status=400)

    reference   = f"WD-{str(uuid.uuid4())[:8].upper()}"
    owner_name  = request.user.get_full_name() or request.user.email
    secret_key  = getattr(settings, 'PAYSTACK_SECRET_KEY', '')

    # ── Attempt real Paystack transfer ────────────────────────
    transfer_code   = None
    transfer_status = "completed"

    if secret_key:
        # Step 1: Create transfer recipient
        recipient_code = resolve_momo_recipient(account, owner_name)

        if recipient_code:
            # Step 2: Initiate transfer
            success, transfer_code, tx_status = initiate_paystack_transfer(
                amount_ghs=amount,
                recipient_code=recipient_code,
                reference=reference,
                reason=f"Master Events withdrawal — {owner_name}",
            )
            if not success:
                return Response(
                    {'error': f'Payout failed: {tx_status}. Please try again or contact support.'},
                    status=400
                )
            # pending = Paystack processing (live mode)
            # success = already done (test mode)
            transfer_status = "completed" if tx_status == "success" else "pending"
            print(f"✅ Paystack transfer initiated: {transfer_code}, status: {tx_status}")
        else:
            # Could not create recipient — still deduct (manual payout fallback)
            print(f"⚠️ Could not create Paystack recipient for {account} — manual payout needed")
            transfer_status = "pending"
    else:
        # No Paystack key — dev/test mode simulation
        print("⚠️ No PAYSTACK_SECRET_KEY — simulating withdrawal")
        transfer_status = "completed"

    # ── Deduct from wallet ────────────────────────────────────
    wallet.balance         -= amount
    wallet.total_withdrawn += amount
    wallet.save()

    # ── Record transaction ────────────────────────────────────
    Transaction.objects.create(
        wallet=wallet,
        type='withdrawal',
        amount=amount,
        description=f"Withdrawal via {'MoMo' if method == 'momo' else 'Bank'} to {account}",
        reference=reference,
        status=transfer_status,
    )

    # ── Notify organizer ──────────────────────────────────────
    try:
        notify_withdrawal(wallet, float(amount), method, reference)
    except Exception as e:
        print(f"Withdrawal email failed: {e}")

    return Response({
        'message':       'Withdrawal initiated successfully' if transfer_status == "pending" else 'Withdrawal completed',
        'amount':        float(amount),
        'reference':     reference,
        'transfer_code': transfer_code,
        'status':        transfer_status,
        'method':        method,
        'account':       account,
        'new_balance':   float(wallet.balance),
    })


# ── Paystack webhook — handles async transfer confirmations ───
@api_view(['POST'])
@permission_classes([AllowAny])
def paystack_webhook(request):
    """
    Paystack sends events here for:
    - charge.success  → payment confirmed (ticket purchase)
    - transfer.success → withdrawal confirmed
    - transfer.failed  → withdrawal failed — refund organizer
    """
    # ── Verify webhook signature ──────────────────────────────
    secret_key = getattr(settings, 'PAYSTACK_SECRET_KEY', '')
    if secret_key:
        sig = request.headers.get('X-Paystack-Signature', '')
        body = request.body
        expected = hmac.new(
            secret_key.encode(),
            body,
            hashlib.sha512
        ).hexdigest()
        if sig != expected:
            print("⚠️ Webhook signature mismatch — ignoring")
            return Response({'status': 'invalid signature'}, status=400)

    try:
        payload = json.loads(request.body)
    except Exception:
        payload = request.data

    event = payload.get('event', '')
    data  = payload.get('data', {})

    print(f"📩 Paystack webhook: {event}")

    # ── Charge success — ticket payment confirmed ─────────────
    if event == 'charge.success':
        reference = data.get('reference', '')
        amount_pesewas = data.get('amount', 0)
        amount_ghs     = Decimal(str(amount_pesewas)) / 100
        print(f"✅ Charge success: ref={reference}, amount=Ghc{amount_ghs}")
        # Ticket creation is already handled in purchase_ticket view
        # This webhook is a backup confirmation — log only

    # ── Transfer success — withdrawal confirmed ───────────────
    elif event == 'transfer.success':
        reference = data.get('reference', '')
        try:
            txn = Transaction.objects.get(reference=reference)
            if txn.status != 'completed':
                txn.status = 'completed'
                txn.save(update_fields=['status'])
                print(f"✅ Transfer confirmed: {reference}")
        except Transaction.DoesNotExist:
            print(f"⚠️ Transfer webhook: transaction {reference} not found")

    # ── Transfer failed — refund wallet ───────────────────────
    elif event == 'transfer.failed':
        reference = data.get('reference', '')
        try:
            txn = Transaction.objects.get(reference=reference)
            if txn.status == 'pending':
                # Refund the wallet
                wallet  = txn.wallet
                wallet.balance         += txn.amount
                wallet.total_withdrawn -= txn.amount
                wallet.save()
                txn.status = 'failed'
                txn.save(update_fields=['status'])
                # Create a refund record
                Transaction.objects.create(
                    wallet=wallet,
                    type='refund',
                    amount=txn.amount,
                    description=f"Refund — transfer failed ({reference})",
                    status='completed',
                )
                print(f"❌ Transfer failed, refunded: {reference}")
        except Transaction.DoesNotExist:
            print(f"⚠️ Transfer failed webhook: transaction {reference} not found")

    return Response({'status': 'ok'})


# ── Transaction history ───────────────────────────────────────
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def transaction_history(request):
    wallet, _ = Wallet.objects.get_or_create(user=request.user)
    transactions = wallet.transactions.all()[:20]
    serializer   = TransactionSerializer(transactions, many=True)
    return Response(serializer.data)