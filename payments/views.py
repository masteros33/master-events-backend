from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from django.conf import settings
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


# ── Initialize transaction ────────────────────────────────────
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def initialize_payment(request):
    amount_raw  = request.data.get('amount', 0)
    event_id    = request.data.get('event_id', '')
    event_name  = request.data.get('event_name', '')
    quantity    = request.data.get('quantity', 1)
    email       = request.user.email

    try:
        amount_ghs     = Decimal(str(float(amount_raw)))
        amount_pesewas = int(amount_ghs * 100)
    except Exception:
        return Response({'error': 'Invalid amount'}, status=400)

    if amount_pesewas < 100:
        return Response({'error': 'Amount too small — minimum is GHS 1'}, status=400)

    if not email or '@' not in email:
        return Response({'error': 'Invalid user email'}, status=400)

    reference  = f"ME-{str(uuid.uuid4())[:12].upper()}"
    secret_key = getattr(settings, 'PAYSTACK_SECRET_KEY', '')

    if not secret_key:
        return Response({'error': 'Payment gateway not configured'}, status=500)

    try:
        resp = requests.post(
            "https://api.paystack.co/transaction/initialize",
            headers=get_paystack_headers(),
            json={
                "email":     email,
                "amount":    amount_pesewas,
                "currency":  "GHS",
                "reference": reference,
                "metadata": {
                    "event_id":   str(event_id),
                    "event_name": str(event_name),
                    "quantity":   str(quantity),
                    "user_id":    str(request.user.id),
                },
            },
            timeout=15,
        )
        data = resp.json()
        print(f"[Paystack] Initialize response: {data}")

        if data.get("status"):
            return Response({
                "access_code": data["data"]["access_code"],
                "reference":   data["data"]["reference"],
            })

        return Response(
            {'error': data.get('message', 'Payment initialization failed')},
            status=400
        )
    except Exception as e:
        print(f"[Paystack] initialize_payment error: {e}")
        return Response({'error': str(e)}, status=500)


def resolve_momo_recipient(phone, name):
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
                "bank_code":      "MTN",
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
    secret_key = getattr(settings, 'PAYSTACK_SECRET_KEY', '')
    if not secret_key:
        return False, None, "Paystack not configured"
    try:
        resp = requests.post(
            "https://api.paystack.co/transfer",
            headers=get_paystack_headers(),
            json={
                "source":    "balance",
                "amount":    int(Decimal(str(amount_ghs)) * 100),
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


# ── Withdraw ──────────────────────────────────────────────────
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def withdraw(request):
    amount_raw = request.data.get('amount', 0)
    method     = request.data.get('method', 'momo')
    account    = request.data.get('account', '').strip()

    try:
        amount = Decimal(str(float(amount_raw)))
    except Exception:
        return Response({'error': 'Invalid amount'}, status=400)

    if amount < 10:
        return Response({'error': 'Minimum withdrawal is GHS 10'}, status=400)

    if not account:
        return Response({'error': 'Account number is required'}, status=400)

    wallet, _ = Wallet.objects.get_or_create(user=request.user)

    if wallet.balance < amount:
        return Response({'error': 'Insufficient balance'}, status=400)

    reference  = f"WD-{str(uuid.uuid4())[:8].upper()}"
    owner_name = request.user.get_full_name() or request.user.email
    secret_key = getattr(settings, 'PAYSTACK_SECRET_KEY', '')

    transfer_code   = None
    transfer_status = "completed"

    if secret_key:
        recipient_code = resolve_momo_recipient(account, owner_name)
        if recipient_code:
            success, transfer_code, tx_status = initiate_paystack_transfer(
                amount_ghs=amount,
                recipient_code=recipient_code,
                reference=reference,
                reason=f"Master Events withdrawal — {owner_name}",
            )
            if not success:
                return Response(
                    {'error': f'Payout failed: {tx_status}. Please try again.'},
                    status=400
                )
            transfer_status = "completed" if tx_status == "success" else "pending"
            print(f"✅ Paystack transfer: {transfer_code}, status: {tx_status}")
        else:
            print(f"⚠️ Could not create recipient for {account} — manual payout needed")
            transfer_status = "pending"
    else:
        print("⚠️ No PAYSTACK_SECRET_KEY — simulating withdrawal")
        transfer_status = "completed"

    wallet.balance         -= amount
    wallet.total_withdrawn += amount
    wallet.save()

    Transaction.objects.create(
        wallet=wallet,
        type='withdrawal',
        amount=amount,
        description=f"Withdrawal via {'MoMo' if method == 'momo' else 'Bank'} to {account}",
        reference=reference,
        status=transfer_status,
    )

    try:
        notify_withdrawal(wallet, float(amount), method, reference)
    except Exception as e:
        print(f"Withdrawal email failed: {e}")

    return Response({
        'message':       'Withdrawal initiated' if transfer_status == "pending" else 'Withdrawal completed',
        'amount':        float(amount),
        'reference':     reference,
        'transfer_code': transfer_code,
        'status':        transfer_status,
        'method':        method,
        'account':       account,
        'new_balance':   float(wallet.balance),
    })


# ── Paystack webhook ──────────────────────────────────────────
@api_view(['POST'])
@permission_classes([AllowAny])
def paystack_webhook(request):
    secret_key = getattr(settings, 'PAYSTACK_SECRET_KEY', '')
    if secret_key:
        sig      = request.headers.get('X-Paystack-Signature', '')
        body     = request.body
        expected = hmac.new(
            secret_key.encode('utf-8'), body, hashlib.sha512
        ).hexdigest()
        if sig != expected:
            print("⚠️ Webhook signature mismatch")
            return Response({'status': 'invalid signature'}, status=400)

    try:
        payload = json.loads(request.body)
    except Exception:
        payload = request.data

    event = payload.get('event', '')
    data  = payload.get('data', {})
    print(f"📩 Paystack webhook: {event}")

    if event == 'charge.success':
        reference      = data.get('reference', '')
        amount_pesewas = data.get('amount', 0)
        metadata       = data.get('metadata', {})
        print(f"✅ Charge success: ref={reference}, amount={amount_pesewas}")

        # Skip if ticket already exists
        from tickets.models import Ticket
        if Ticket.objects.filter(payment_reference=reference).exists():
            print(f"⚠️ Ticket already exists for {reference} — skipping webhook creation")
            return Response({'status': 'ok'})

        try:
            event_id  = int(metadata.get('event_id', 0))
            quantity  = int(metadata.get('quantity', 1))
            user_id   = int(metadata.get('user_id', 0))
        except (ValueError, TypeError) as e:
            print(f"⚠️ Webhook metadata parse error: {e}")
            return Response({'status': 'ok'})

        if not event_id or not user_id:
            print(f"⚠️ Webhook missing event_id or user_id in metadata")
            return Response({'status': 'ok'})

        try:
            from events.models import Event
            from accounts.models import User
            from tickets.views import generate_and_upload_qr
            from utils.emails import notify_ticket_purchase
            from utils.blockchain import mint_ticket_nft_async

            event_obj  = Event.objects.get(pk=event_id)
            user_obj   = User.objects.get(pk=user_id)
            amount_ghs = Decimal(str(amount_pesewas)) / 100

            ticket = Ticket(
                event=event_obj,
                owner=user_obj,
                original_buyer=user_obj,
                quantity=quantity,
                price_paid=amount_ghs,
                payment_reference=reference,
                status='active',
            )
            ticket.save()

            qr_url, _ = generate_and_upload_qr(ticket)
            if qr_url:
                ticket.qr_image = qr_url
                ticket.save(update_fields=['qr_image'])

            event_obj.tickets_sold += quantity
            event_obj.save(update_fields=['tickets_sold'])

            organizer_wallet, _ = Wallet.objects.get_or_create(user=event_obj.organizer)
            organizer_amount = amount_ghs * Decimal('0.95')
            organizer_wallet.balance      += organizer_amount
            organizer_wallet.total_earned += organizer_amount
            organizer_wallet.save()

            Transaction.objects.create(
                wallet=organizer_wallet,
                type='sale',
                amount=organizer_amount,
                description=f"{quantity}x {event_obj.name} (webhook)",
                reference=reference,
                status='completed',
            )

            try:
                notify_ticket_purchase(ticket)
            except Exception as e:
                print(f"Webhook email failed: {e}")

            try:
                def on_mint(nft_result):
                    try:
                        t = Ticket.objects.get(pk=ticket.pk)
                        t.nft_token_id  = nft_result['token_id']
                        t.nft_tx_hash   = nft_result['tx_hash']
                        t.nft_token_uri = nft_result['token_uri']
                        t.save(update_fields=['nft_token_id','nft_tx_hash','nft_token_uri'])
                    except Exception as e:
                        print(f"Webhook NFT save error: {e}")
                mint_ticket_nft_async(ticket, callback=on_mint)
            except Exception as e:
                print(f"Webhook NFT mint failed: {e}")

            print(f"✅ Webhook created ticket {ticket.ticket_id} for {user_obj.email}")

        except Event.DoesNotExist:
            print(f"⚠️ Webhook: event {event_id} not found")
            return Response({'status': 'ok'})
        except User.DoesNotExist:
            print(f"⚠️ Webhook: user {user_id} not found")
            return Response({'status': 'ok'})
        except Exception as e:
            print(f"⚠️ Webhook ticket creation error: {e}")
            return Response({'status': 'ok'})

    # ── Always return 200 to Paystack ─────────────────────────
    return Response({'status': 'ok'})


# ── Transaction history ───────────────────────────────────────
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def transaction_history(request):
    wallet, _ = Wallet.objects.get_or_create(user=request.user)
    transactions = wallet.transactions.all()[:20]
    serializer   = TransactionSerializer(transactions, many=True)
    return Response(serializer.data)