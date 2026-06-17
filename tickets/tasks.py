from django_q.tasks import async_task


def task_mint_nft(ticket_id):
    """Mint NFT for a ticket — runs in Q worker"""
    try:
        from tickets.models import Ticket
        from utils.blockchain import mint_ticket_nft
        from utils.emails import notify_nft_minted

        ticket = Ticket.objects.get(pk=ticket_id)
        print(f"[Q] Minting NFT for ticket {ticket.ticket_id}...")

        result = mint_ticket_nft(ticket)
        if result:
            ticket.nft_token_id    = result['token_id']
            ticket.nft_tx_hash     = result['tx_hash']
            ticket.nft_token_uri   = result['token_uri']
            ticket.nft_mint_failed = False
            ticket.save(update_fields=[
                'nft_token_id', 'nft_tx_hash',
                'nft_token_uri', 'nft_mint_failed',
            ])
            print(f"✅ [Q] NFT minted for {ticket.ticket_id}: {result['tx_hash'][:16]}...")
            try:
                notify_nft_minted(ticket)
            except Exception as e:
                print(f"NFT email failed: {e}")
        else:
            ticket.nft_mint_failed = True
            ticket.save(update_fields=['nft_mint_failed'])
            print(f"⚠️ [Q] NFT mint failed for {ticket.ticket_id} — marked for retry")

    except Exception as e:
        print(f"❌ [Q] task_mint_nft error: {e}")
        raise


def task_send_ticket_purchase_email(ticket_id, static_qr_base64=None):
    """Send purchase confirmation email — static_qr_base64 reserved for PDF attachment (Phase 2)"""
    try:
        from tickets.models import Ticket
        from utils.emails import notify_ticket_purchase
        ticket = Ticket.objects.get(pk=ticket_id)
        notify_ticket_purchase(ticket, static_qr_base64=static_qr_base64)
        print(f"✅ [Q] Purchase email sent for {ticket.ticket_id}")
    except Exception as e:
        print(f"❌ [Q] task_send_ticket_purchase_email error: {e}")
        raise


def task_send_transfer_email(ticket_id, from_user_id, to_user_id, new_ticket_id=None, static_qr_base64=None):
    """Send transfer emails to both parties"""
    try:
        from tickets.models import Ticket
        from accounts.models import User
        from utils.emails import notify_ticket_transfer
        ticket    = Ticket.objects.get(pk=ticket_id)
        from_user = User.objects.get(pk=from_user_id)
        to_user   = User.objects.get(pk=to_user_id)

        new_ticket = None
        if new_ticket_id:
            try:
                new_ticket = Ticket.objects.get(pk=new_ticket_id)
            except Ticket.DoesNotExist:
                new_ticket = None

        notify_ticket_transfer(ticket, from_user, to_user, new_ticket=new_ticket, static_qr_base64=static_qr_base64)
        print(f"✅ [Q] Transfer emails sent for {ticket.ticket_id}")
    except Exception as e:
        print(f"❌ [Q] task_send_transfer_email error: {e}")
        raise


def task_send_resale_notifications(ticket_id, seller_id, buyer_id, seller_amount):
    """Send resale sold + purchased emails"""
    try:
        from tickets.models import Ticket
        from accounts.models import User
        from utils.emails import notify_resale_sold, notify_resale_purchased
        from decimal import Decimal
        ticket = Ticket.objects.get(pk=ticket_id)
        seller = User.objects.get(pk=seller_id)
        buyer  = User.objects.get(pk=buyer_id)
        notify_resale_sold(ticket, seller, buyer, Decimal(str(seller_amount)))
        notify_resale_purchased(ticket, buyer)
        print(f"✅ [Q] Resale emails sent for {ticket.ticket_id}")
    except Exception as e:
        print(f"❌ [Q] task_send_resale_notifications error: {e}")
        raise


def task_send_door_code_email(event_id, organizer_id, code):
    """Email organizer their door code"""
    try:
        from events.models import Event
        from accounts.models import User
        from utils.emails import notify_door_code_generated
        event     = Event.objects.get(pk=event_id)
        organizer = User.objects.get(pk=organizer_id)
        notify_door_code_generated(event, organizer, code)
        print(f"✅ [Q] Door code email sent for event {event.name}")
    except Exception as e:
        print(f"❌ [Q] task_send_door_code_email error: {e}")
        raise


def task_send_ticket_redeemed_notification(ticket_id):
    """Notify ticket owner when scanned at gate"""
    try:
        from tickets.models import Ticket
        from utils.emails import send_notification
        ticket = Ticket.objects.get(pk=ticket_id)
        send_notification(
            user=ticket.owner,
            type='ticket_redeemed',
            title='Ticket Scanned — Enjoy the Event! 🎉',
            body=(
                f"Hi {ticket.owner.first_name},\n\n"
                f"Your ticket for {ticket.event.name} was just scanned at the gate.\n\n"
                f"📅 {ticket.event.date} · 📍 {ticket.event.venue}\n\n"
                f"Enjoy the event! 🎉"
            ),
            send_email=True,
            icon="🎉",
        )
        print(f"✅ [Q] Redeemed notification sent for {ticket.ticket_id}")
    except Exception as e:
        print(f"❌ [Q] task_send_ticket_redeemed_notification error: {e}")
        raise


def task_send_resale_listed_email(ticket_id, user_id):
    """Email seller when ticket is listed"""
    try:
        from tickets.models import Ticket
        from accounts.models import User
        from utils.emails import notify_resale_listed
        ticket = Ticket.objects.get(pk=ticket_id)
        user   = User.objects.get(pk=user_id)
        notify_resale_listed(ticket, user)
        print(f"✅ [Q] Resale listed email sent for {ticket.ticket_id}")
    except Exception as e:
        print(f"❌ [Q] task_send_resale_listed_email error: {e}")
        raise


def task_retry_failed_mints():
    """Retry all failed NFT mints — schedule this in Django admin"""
    try:
        from utils.blockchain import retry_failed_mints
        retry_failed_mints()
    except Exception as e:
        print(f"❌ [Q] task_retry_failed_mints error: {e}")
        raise






def task_send_registration_email(registration_id, static_qr_base64=None):
    """Send free event registration confirmation email"""
    try:
        from tickets.models import Registration
        from utils.emails import notify_free_registration
        reg = Registration.objects.select_related('event', 'attendee').get(pk=registration_id)
        notify_free_registration(reg, static_qr_base64=static_qr_base64)
        print(f"✅ [Q] Registration email sent for {reg.registration_id}")
    except Exception as e:
        print(f"❌ [Q] task_send_registration_email error: {e}")
        raise