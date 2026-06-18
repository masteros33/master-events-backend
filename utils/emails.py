import resend
import threading
from django.conf import settings
from accounts.models import Notification


def _send_email_async(to_email, subject, html, text):
    def _send():
        try:
            resend.api_key = settings.RESEND_API_KEY
            params = {
                "from":    settings.DEFAULT_FROM_EMAIL,
                "to":      [to_email],
                "subject": subject,
                "html":    html,
                "text":    text,
            }
            r = resend.Emails.send(params)
            print(f"✅ Email sent via Resend: {r}")
        except Exception as e:
            print(f"❌ Resend email error: {e}")
    threading.Thread(target=_send, daemon=True).start()


def _build_html(title, body, action_url=None, action_label="View Ticket →", icon="🎟️"):
    action_button = ""
    if action_url:
        action_button = f"""
        <div style="text-align:center;margin:24px 0;">
            <a href="{action_url}"
               style="background:linear-gradient(135deg,#f5a623,#e8920f);color:#fff;padding:14px 32px;border-radius:12px;text-decoration:none;font-weight:700;font-size:15px;display:inline-block;">
                {action_label}
            </a>
        </div>
        """
    return f"""
    <!DOCTYPE html>
    <html>
    <head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"></head>
    <body style="margin:0;padding:0;background:#0f0f0f;font-family:'Helvetica Neue',Arial,sans-serif;">
        <div style="max-width:600px;margin:0 auto;padding:24px 16px;">
            <div style="background:linear-gradient(135deg,#f5a623,#e8920f);border-radius:20px 20px 0 0;padding:32px;text-align:center;">
                <div style="font-size:32px;margin-bottom:8px;">{icon}</div>
                <h1 style="margin:0;color:#fff;font-size:24px;font-weight:900;letter-spacing:-0.5px;">Master Events</h1>
                <p style="margin:6px 0 0;color:rgba(255,255,255,0.8);font-size:12px;letter-spacing:2px;text-transform:uppercase;">NFT-Powered Event Ticketing</p>
            </div>
            <div style="background:#1a1a1a;padding:32px;border-left:1px solid #2a2a2a;border-right:1px solid #2a2a2a;">
                <h2 style="color:#f5a623;margin:0 0 16px;font-size:20px;font-weight:800;">{title}</h2>
                <p style="color:rgba(255,255,255,0.75);line-height:1.8;margin:0 0 20px;font-size:15px;white-space:pre-line;">{body}</p>
                {action_button}
                <div style="background:rgba(124,58,237,0.1);border:1px solid rgba(124,58,237,0.25);border-radius:12px;padding:14px 16px;margin-top:24px;">
                    <span style="font-size:16px;">⛓️</span>
                    <span style="color:#a78bfa;font-weight:700;font-size:11px;letter-spacing:0.5px;margin-left:8px;">SECURED BY POLYGON BLOCKCHAIN</span>
                    <div style="color:rgba(255,255,255,0.4);font-size:11px;margin-top:4px;">All tickets are NFTs — impossible to fake or duplicate</div>
                </div>
            </div>
            <div style="background:#111;border-radius:0 0 20px 20px;border:1px solid #2a2a2a;border-top:none;padding:20px 32px;text-align:center;">
                <p style="color:rgba(255,255,255,0.25);font-size:11px;margin:0 0 4px;">© 2026 Master Events · masterevents.events</p>
                <p style="color:rgba(255,255,255,0.15);font-size:10px;margin:0;">You received this because you have a Master Events account.</p>
            </div>
        </div>
    </body>
    </html>
    """


def send_notification(user, type, title, body, send_email=True, action_url=None, action_label="View Ticket →", icon="🎟️"):
    """Create in-app notification and optionally send email"""
    Notification.objects.create(user=user, type=type, title=title, body=body)
    if send_email and user.email:
        html = _build_html(title, body, action_url, action_label, icon)
        _send_email_async(
            to_email=user.email,
            subject=f"Master Events — {title}",
            html=html,
            text=body,
        )


def notify_welcome(user):
    app_url = getattr(settings, 'FRONTEND_URL', 'https://master-events-bi7m.vercel.app')
    html = f"""
    <!DOCTYPE html>
    <html>
    <head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"></head>
    <body style="margin:0;padding:0;background:#0f0f0f;font-family:'Helvetica Neue',Arial,sans-serif;">
        <div style="max-width:600px;margin:0 auto;padding:24px 16px;">
            <div style="background:linear-gradient(135deg,#f5a623,#e8920f);border-radius:20px 20px 0 0;padding:40px 32px;text-align:center;">
                <div style="font-size:48px;margin-bottom:12px;">🎟️</div>
                <h1 style="margin:0;color:#fff;font-size:26px;font-weight:900;letter-spacing:-0.5px;">Welcome to Master Events!</h1>
                <p style="margin:8px 0 0;color:rgba(255,255,255,0.85);font-size:14px;">NFT-powered ticketing · masterevents.events</p>
            </div>
            <div style="background:#1a1a1a;padding:32px;border-left:1px solid #2a2a2a;border-right:1px solid #2a2a2a;">
                <p style="color:rgba(255,255,255,0.85);font-size:16px;line-height:1.7;margin:0 0 24px;">
                    Hi <strong style="color:#fff;">{user.first_name}</strong> 👋,<br><br>
                    You're now part of Master Events — where every ticket is an NFT on the Polygon blockchain.
                    No fakes. No scalping. Just real tickets, owned by you.
                </p>
                <div style="text-align:center;margin-bottom:20px;">
                    <a href="{app_url}" style="background:linear-gradient(135deg,#f5a623,#e8920f);color:#fff;padding:16px 48px;border-radius:14px;text-decoration:none;font-weight:700;font-size:16px;display:inline-block;">
                        Browse Events →
                    </a>
                </div>
            </div>
            <div style="background:#111;border-radius:0 0 20px 20px;border:1px solid #2a2a2a;border-top:none;padding:20px 32px;text-align:center;">
                <p style="color:rgba(255,255,255,0.2);font-size:11px;margin:0;">© 2026 Master Events · masterevents.events</p>
            </div>
        </div>
    </body>
    </html>
    """
    _send_email_async(
        to_email=user.email,
        subject="Welcome to Master Events! 🎟️",
        html=html,
        text=f"Hi {user.first_name},\n\nWelcome to Master Events!\nEvery ticket is an NFT on Polygon.\n\nBrowse events: {app_url}",
    )


# ── KEY FIX: added static_qr_base64=None param ───────────────
def notify_ticket_purchase(ticket, static_qr_base64=None):
    """
    Paid event: confirmation email only — NO QR image.
    QR lives in the app only (rotating HMAC, screenshot-proof).
    """
    user        = ticket.owner
    event       = ticket.event
    app_url     = getattr(settings, 'FRONTEND_URL', 'https://master-events-bi7m.vercel.app')
    event_image = getattr(event, 'image', '') or ''
    currency    = getattr(event, 'currency', 'GHS')

    image_block = f"""
    <div style="border-radius:12px;overflow:hidden;margin-bottom:20px;">
        <img src="{event_image}" alt="{event.name}"
             style="width:100%;height:180px;object-fit:cover;display:block;"/>
    </div>
    """ if event_image else ""

    html = f"""
    <!DOCTYPE html>
    <html>
    <head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"></head>
    <body style="margin:0;padding:0;background:#f5f5f5;font-family:'Inter','Helvetica Neue',Arial,sans-serif;">
      <div style="max-width:560px;margin:0 auto;padding:24px 16px;">

        <!-- Header -->
        <div style="background:linear-gradient(135deg,#F97316,#EA6C0A);border-radius:16px 16px 0 0;padding:28px 32px;text-align:center;">
          <div style="font-size:32px;margin-bottom:8px;">🎟️</div>
          <h1 style="margin:0;color:#fff;font-size:20px;font-weight:700;letter-spacing:-0.3px;">Booking Confirmed</h1>
          <p style="margin:6px 0 0;color:rgba(255,255,255,0.8);font-size:12px;">masterevents.events</p>
        </div>

        <!-- Body -->
        <div style="background:#fff;padding:28px 32px;border-left:1px solid #e5e7eb;border-right:1px solid #e5e7eb;">
          <p style="color:#374151;font-size:15px;margin:0 0 20px;">
            Hi <strong>{user.first_name}</strong>, your payment was successful!
          </p>

          {image_block}

          <!-- Ticket details table -->
          <div style="background:#f9fafb;border:1px solid #e5e7eb;border-radius:10px;overflow:hidden;margin-bottom:20px;">
            <div style="padding:12px 16px;border-bottom:1px solid #e5e7eb;display:flex;justify-content:space-between;">
              <span style="color:#6b7280;font-size:13px;">Event</span>
              <span style="color:#111;font-size:13px;font-weight:600;text-align:right;max-width:60%;">{event.name}</span>
            </div>
            <div style="padding:12px 16px;border-bottom:1px solid #e5e7eb;display:flex;justify-content:space-between;">
              <span style="color:#6b7280;font-size:13px;">Date</span>
              <span style="color:#111;font-size:13px;">{event.date}</span>
            </div>
            <div style="padding:12px 16px;border-bottom:1px solid #e5e7eb;display:flex;justify-content:space-between;">
              <span style="color:#6b7280;font-size:13px;">Venue</span>
              <span style="color:#111;font-size:13px;">{event.venue}</span>
            </div>
            <div style="padding:12px 16px;border-bottom:1px solid #e5e7eb;display:flex;justify-content:space-between;">
              <span style="color:#6b7280;font-size:13px;">Ticket ID</span>
              <span style="color:#F97316;font-size:13px;font-weight:700;font-family:monospace;">{ticket.ticket_id}</span>
            </div>
            <div style="padding:12px 16px;border-bottom:1px solid #e5e7eb;display:flex;justify-content:space-between;">
              <span style="color:#6b7280;font-size:13px;">Quantity</span>
              <span style="color:#111;font-size:13px;">{ticket.quantity} ticket(s)</span>
            </div>
            <div style="padding:12px 16px;display:flex;justify-content:space-between;">
              <span style="color:#6b7280;font-size:13px;">Amount Paid</span>
              <span style="color:#111;font-size:13px;font-weight:600;">{currency} {ticket.price_paid}</span>
            </div>
          </div>

          <!-- Important notice — QR is in app only -->
          <div style="background:#fef3c7;border:1px solid #fde68a;border-radius:10px;padding:14px 16px;margin-bottom:20px;">
            <div style="font-weight:700;font-size:12px;color:#92400e;margin-bottom:4px;">📱 Show your QR at the gate</div>
            <div style="font-size:12px;color:#78350f;line-height:1.6;">
              Your entry QR code is in the Master Events app — it rotates every 10 seconds for security.
              <strong>Do not screenshot it</strong>. Open the app at the gate for instant scanning.
            </div>
          </div>

          <!-- Blockchain notice -->
          <div style="background:#f5f3ff;border:1px solid #ddd6fe;border-radius:10px;padding:14px 16px;margin-bottom:24px;">
            <div style="font-weight:700;font-size:11px;color:#5b21b6;margin-bottom:3px;">⛓️ NFT MINTING ON POLYGON</div>
            <div style="font-size:12px;color:#6d28d9;">Your ticket is being minted as an NFT — permanent, unforgeable, yours forever.</div>
          </div>

          <div style="text-align:center;">
            <a href="{app_url}" style="background:linear-gradient(135deg,#F97316,#EA6C0A);color:#fff;padding:13px 36px;border-radius:10px;text-decoration:none;font-weight:600;font-size:14px;display:inline-block;">
              Open App to View QR →
            </a>
          </div>
        </div>

        <!-- Footer -->
        <div style="background:#f9fafb;border-radius:0 0 16px 16px;border:1px solid #e5e7eb;border-top:none;padding:16px 32px;text-align:center;">
          <p style="color:#9ca3af;font-size:11px;margin:0;">© 2026 Master Events · masterevents.events · Secured by Polygon</p>
        </div>

      </div>
    </body>
    </html>
    """

    _send_email_async(
        to_email=user.email,
        subject=f"🎟️ Booking Confirmed — {event.name}",
        html=html,
        text=(
            f"Hi {user.first_name},\n\n"
            f"Your booking for {event.name} is confirmed!\n\n"
            f"Ticket ID: {ticket.ticket_id}\n"
            f"Quantity: {ticket.quantity}\n"
            f"Amount: {currency} {ticket.price_paid}\n"
            f"Date: {event.date}\n"
            f"Venue: {event.venue}\n\n"
            f"⚠️ Your QR code is in the app only — open it at the gate.\n\n"
            f"Open the app: {app_url}"
        ),
    )

    # Notify organizer
    send_notification(
        user=event.organizer,
        type='sale',
        title=f'New Sale — {event.name} 💰',
        body=(
            f"Hi {event.organizer.first_name},\n\n"
            f"{user.get_full_name() or user.email} just purchased "
            f"{ticket.quantity} ticket(s) for {event.name}.\n\n"
            f"💰 {currency} {float(ticket.price_paid) * 0.95:.2f} added to your wallet.\n"
            f"🎟️ Ticket ID: {ticket.ticket_id}"
        ),
        send_email=True,
        action_url=getattr(settings, 'FRONTEND_URL', 'https://master-events-bi7m.vercel.app'),
        action_label="View Dashboard →",
        icon="💰",
    )

# ── KEY FIX: added new_ticket=None, static_qr_base64=None params ──
def notify_ticket_transfer(ticket, from_user, to_user, new_ticket=None, static_qr_base64=None):
    app_url = getattr(settings, 'FRONTEND_URL', 'https://master-events-bi7m.vercel.app')

    static_qr_block = f"""
    <div style="text-align:center;margin:16px 0;background:rgba(245,166,35,0.05);border:1px solid rgba(245,166,35,0.15);border-radius:14px;padding:16px;">
        <p style="color:rgba(255,255,255,0.5);font-size:11px;margin:0 0 10px;text-transform:uppercase;letter-spacing:1px;">Your New Emergency Backup QR</p>
        <img src="data:image/png;base64,{static_qr_base64}" style="width:160px;height:160px;border-radius:10px;background:#fff;padding:6px;" />
        <p style="color:rgba(255,255,255,0.3);font-size:10px;margin:8px 0 0;">Single-use · Invalidates on transfer</p>
    </div>
    """ if static_qr_base64 else ""

    send_notification(
        user=from_user,
        type='transfer_sent',
        title='Ticket Transferred ✅',
        body=(
            f"Hi {from_user.first_name},\n\n"
            f"Your ticket for {ticket.event.name} has been successfully transferred to "
            f"{to_user.get_full_name() or to_user.email}.\n\n"
            f"📅 Event: {ticket.event.date} at {ticket.event.venue}\n"
            f"🎟️ Ticket ID: {ticket.ticket_id}\n\n"
            f"Your QR code for this ticket is now void."
        ),
        send_email=True,
        icon="✅",
        action_label="View My Tickets →",
        action_url=app_url,
    )

    # Email to receiver with new static QR if available
    if new_ticket and static_qr_base64:
        html = f"""
        <!DOCTYPE html>
        <html>
        <head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"></head>
        <body style="margin:0;padding:0;background:#0f0f0f;font-family:'Helvetica Neue',Arial,sans-serif;">
            <div style="max-width:600px;margin:0 auto;padding:24px 16px;">
                <div style="background:linear-gradient(135deg,#f5a623,#e8920f);border-radius:20px 20px 0 0;padding:28px 32px;text-align:center;">
                    <div style="font-size:36px;margin-bottom:8px;">🎟️</div>
                    <h1 style="margin:0;color:#fff;font-size:22px;font-weight:900;">You Received a Ticket!</h1>
                    <p style="margin:6px 0 0;color:rgba(255,255,255,0.85);font-size:13px;">{ticket.event.name}</p>
                </div>
                <div style="background:#1a1a1a;padding:28px 32px;border-left:1px solid #2a2a2a;border-right:1px solid #2a2a2a;">
                    <p style="color:rgba(255,255,255,0.8);font-size:15px;margin:0 0 20px;">
                        Hi <strong style="color:#fff;">{to_user.first_name}</strong>,<br><br>
                        {from_user.get_full_name() or from_user.email} just transferred a ticket to you!
                    </p>
                    <div style="background:#111;border:1px solid #2a2a2a;border-radius:14px;padding:18px;margin-bottom:20px;">
                        <div style="display:flex;justify-content:space-between;padding:8px 0;border-bottom:1px solid #222;">
                            <span style="color:rgba(255,255,255,0.4);font-size:13px;">Event</span>
                            <span style="color:#fff;font-size:13px;font-weight:700;">{ticket.event.name}</span>
                        </div>
                        <div style="display:flex;justify-content:space-between;padding:8px 0;border-bottom:1px solid #222;">
                            <span style="color:rgba(255,255,255,0.4);font-size:13px;">Date</span>
                            <span style="color:#fff;font-size:13px;">{ticket.event.date}</span>
                        </div>
                        <div style="display:flex;justify-content:space-between;padding:8px 0;">
                            <span style="color:rgba(255,255,255,0.4);font-size:13px;">Venue</span>
                            <span style="color:#fff;font-size:13px;">{ticket.event.venue}</span>
                        </div>
                    </div>
                    {static_qr_block}
                    <div style="text-align:center;">
                        <a href="{app_url}" style="background:linear-gradient(135deg,#f5a623,#e8920f);color:#fff;padding:14px 40px;border-radius:12px;text-decoration:none;font-weight:700;font-size:15px;display:inline-block;">
                            View My Ticket →
                        </a>
                    </div>
                </div>
                <div style="background:#111;border-radius:0 0 20px 20px;border:1px solid #2a2a2a;border-top:none;padding:20px 32px;text-align:center;">
                    <p style="color:rgba(255,255,255,0.2);font-size:11px;margin:0;">© 2026 Master Events · masterevents.events</p>
                </div>
            </div>
        </body>
        </html>
        """
        _send_email_async(
            to_email=to_user.email,
            subject=f"🎟️ You Received a Ticket — {ticket.event.name}",
            html=html,
            text=(
                f"Hi {to_user.first_name},\n\n"
                f"{from_user.get_full_name() or from_user.email} transferred a ticket to you!\n\n"
                f"Event: {ticket.event.name}\n"
                f"Date: {ticket.event.date}\n"
                f"Venue: {ticket.event.venue}\n\n"
                f"Open Master Events to view your QR: {app_url}"
            ),
        )
    else:
        send_notification(
            user=to_user,
            type='transfer_received',
            title='You Received a Ticket! 🎟️',
            body=(
                f"Hi {to_user.first_name},\n\n"
                f"{from_user.get_full_name() or from_user.email} transferred a ticket to you!\n\n"
                f"🎫 Event: {ticket.event.name}\n"
                f"📅 Date: {ticket.event.date}\n"
                f"📍 Venue: {ticket.event.venue}\n\n"
                f"Log in to Master Events to view your QR code and NFT ownership."
            ),
            send_email=True,
            action_url=app_url,
            action_label="View My Ticket →",
            icon="🎟️",
        )


def notify_resale_listed(ticket, user):
    app_url = getattr(settings, 'FRONTEND_URL', 'https://master-events-bi7m.vercel.app')
    send_notification(
        user=user,
        type='resale_listed',
        title='Ticket Listed for Resale 🏷️',
        body=(
            f"Hi {user.first_name},\n\n"
            f"Your ticket for {ticket.event.name} is now live on the resale marketplace "
            f"at {getattr(ticket.event, 'currency', 'GHS')} {ticket.resale_price}.\n\n"
            f"📅 Event: {ticket.event.date} at {ticket.event.venue}\n"
            f"💰 You keep 98% when it sells — we only take 2%.\n\n"
            f"You'll get an email the moment it sells."
        ),
        send_email=True,
        action_url=app_url,
        action_label="View Marketplace →",
        icon="🏷️",
    )


def notify_resale_sold(ticket, seller, buyer, seller_amount):
    app_url = getattr(settings, 'FRONTEND_URL', 'https://master-events-bi7m.vercel.app')
    send_notification(
        user=seller,
        type='resale_sold',
        title='Your Ticket Sold! 💰',
        body=(
            f"Hi {seller.first_name},\n\n"
            f"Your resale ticket for {ticket.event.name} just sold!\n\n"
            f"🎫 Event: {ticket.event.name}\n"
            f"📅 Date: {ticket.event.date}\n"
            f"💰 {getattr(ticket.event, 'currency', 'GHS')} {float(seller_amount):.2f} added to your wallet (98% payout).\n\n"
            f"Withdraw anytime from your Wallet tab."
        ),
        send_email=True,
        action_url=app_url,
        action_label="View Wallet →",
        icon="💰",
    )


def notify_resale_purchased(new_ticket, buyer):
    app_url = getattr(settings, 'FRONTEND_URL', 'https://master-events-bi7m.vercel.app')
    event   = new_ticket.event
    send_notification(
        user=buyer,
        type='resale_purchased',
        title='Resale Ticket Confirmed! 🎟️',
        body=(
            f"Hi {buyer.first_name},\n\n"
            f"You successfully purchased a resale ticket for {event.name}!\n\n"
            f"🎫 Event: {event.name}\n"
            f"📅 Date: {event.date}\n"
            f"📍 Venue: {event.venue}\n"
            f"🎟️ Ticket ID: {new_ticket.ticket_id}\n\n"
            f"NFT ownership has been transferred to you on Polygon.\n"
            f"Open the app to view your QR code."
        ),
        send_email=True,
        action_url=app_url,
        action_label="View My Ticket →",
        icon="🎟️",
    )


def notify_nft_minted(ticket):
    app_url  = getattr(settings, 'FRONTEND_URL', 'https://master-events-bi7m.vercel.app')
    explorer = f"https://amoy.polygonscan.com/tx/{ticket.nft_tx_hash}" if ticket.nft_tx_hash else None
    body = (
        f"Hi {ticket.owner.first_name},\n\n"
        f"Your NFT ticket for {ticket.event.name} has been confirmed on the Polygon blockchain!\n\n"
        f"🎟️ Ticket ID: {ticket.ticket_id}\n"
        f"⛓️ Token ID: #{ticket.nft_token_id or 'Confirmed'}\n"
        f"🔗 TX: {ticket.nft_tx_hash or 'N/A'}\n\n"
        f"Your ticket ownership is now permanently recorded on-chain."
    )
    send_notification(
        user=ticket.owner,
        type='nft_minted',
        title='NFT Confirmed on Polygon ⛓️',
        body=body,
        send_email=True,
        action_url=explorer or app_url,
        action_label="Verify on Polygonscan ↗",
        icon="⛓️",
    )


def notify_door_code_generated(event, organizer, code):
    send_notification(
        user=organizer,
        type='door_code',
        title='Door Staff Code Generated 🚪',
        body=(
            f"Hi {organizer.first_name},\n\n"
            f"A new door staff access code has been generated for {event.name}.\n\n"
            f"🔑 Code: {code}\n"
            f"⚠️ Single-use — expires after first login.\n\n"
            f"Share this code only with your door staff."
        ),
        send_email=True,
        icon="🚪",
    )


def notify_withdrawal(wallet, amount, method, reference):
    send_notification(
        user=wallet.user,
        type='withdrawal',
        title='Withdrawal Initiated 💸',
        body=(
            f"Hi {wallet.user.first_name},\n\n"
            f"Your withdrawal of GHS {amount} via {method} has been initiated.\n\n"
            f"📋 Reference: {reference}\n"
            f"⏱️ Funds arrive within 5-10 minutes."
        ),
        send_email=True,
        icon="💸",
    )


def notify_password_reset(user, reset_url):
    html = f"""
    <!DOCTYPE html>
    <html>
    <head><meta charset="UTF-8"></head>
    <body style="margin:0;padding:0;background:#0f0f0f;font-family:Arial,sans-serif;">
        <div style="max-width:600px;margin:0 auto;padding:24px 16px;">
            <div style="background:linear-gradient(135deg,#f5a623,#e8920f);border-radius:20px 20px 0 0;padding:32px;text-align:center;">
                <div style="font-size:32px;margin-bottom:8px;">🔐</div>
                <h1 style="margin:0;color:#fff;font-size:22px;font-weight:900;">Reset Your Password</h1>
                <p style="margin:6px 0 0;color:rgba(255,255,255,0.8);font-size:12px;">Master Events · masterevents.events</p>
            </div>
            <div style="background:#1a1a1a;padding:32px;border:1px solid #2a2a2a;border-top:none;">
                <p style="color:rgba(255,255,255,0.75);font-size:15px;line-height:1.8;margin:0 0 24px;">
                    Hi {user.first_name},<br><br>
                    We received a request to reset your Master Events password.
                    Click below — this link expires in <strong style="color:#f5a623;">30 minutes</strong>.
                </p>
                <div style="text-align:center;margin:28px 0;">
                    <a href="{reset_url}" style="background:linear-gradient(135deg,#f5a623,#e8920f);color:#fff;padding:16px 40px;border-radius:12px;text-decoration:none;font-weight:700;font-size:16px;display:inline-block;">
                        Reset Password →
                    </a>
                </div>
                <p style="color:rgba(255,255,255,0.35);font-size:12px;">If you didn't request this, ignore this email.</p>
            </div>
            <div style="background:#111;border-radius:0 0 20px 20px;border:1px solid #2a2a2a;border-top:none;padding:16px;text-align:center;">
                <p style="color:rgba(255,255,255,0.2);font-size:10px;margin:0;">© 2026 Master Events · masterevents.events</p>
            </div>
        </div>
    </body>
    </html>
    """
    _send_email_async(
        to_email=user.email,
        subject="Master Events — Reset Your Password",
        html=html,
        text=f"Hi {user.first_name},\n\nReset your password (expires in 30 minutes):\n{reset_url}\n\nIf you didn't request this, ignore this email.",
    )
    return True


def notify_free_registration(reg, static_qr_base64=None):
    """Email attendee their free event registration pass"""
    user    = reg.attendee
    event   = reg.event
    app_url = getattr(settings, 'FRONTEND_URL', 'https://master-events-bi7m.vercel.app')

    static_qr_block = f"""
    <div style="text-align:center;margin-bottom:20px;">
        <p style="color:rgba(255,255,255,0.5);font-size:12px;margin-bottom:8px;">Show this QR at the entrance</p>
        <img src="data:image/png;base64,{static_qr_base64}" style="width:180px;height:180px;border-radius:12px;background:#fff;padding:8px;" />
    </div>
    """ if static_qr_base64 else ""

    html = f"""
    <!DOCTYPE html>
    <html>
    <head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"></head>
    <body style="margin:0;padding:0;background:#0f0f0f;font-family:'Helvetica Neue',Arial,sans-serif;">
        <div style="max-width:600px;margin:0 auto;padding:24px 16px;">
            <div style="background:linear-gradient(135deg,#f5a623,#e8920f);border-radius:20px 20px 0 0;padding:28px 32px;text-align:center;">
                <div style="font-size:36px;margin-bottom:8px;">🎟️</div>
                <h1 style="margin:0;color:#fff;font-size:22px;font-weight:900;">You're Registered!</h1>
                <p style="margin:6px 0 0;color:rgba(255,255,255,0.85);font-size:13px;">Your entry pass for {event.name}</p>
            </div>
            <div style="background:#1a1a1a;padding:28px 32px;border-left:1px solid #2a2a2a;border-right:1px solid #2a2a2a;">
                <p style="color:rgba(255,255,255,0.8);font-size:15px;margin:0 0 20px;">
                    Hi <strong style="color:#fff;">{user.first_name}</strong>, your spot is confirmed!
                </p>
                <div style="background:#111;border:1px solid #2a2a2a;border-radius:14px;padding:18px;margin-bottom:20px;">
                    <div style="display:flex;justify-content:space-between;padding:8px 0;border-bottom:1px solid #222;">
                        <span style="color:rgba(255,255,255,0.4);font-size:13px;">Event</span>
                        <span style="color:#fff;font-size:13px;font-weight:700;">{event.name}</span>
                    </div>
                    <div style="display:flex;justify-content:space-between;padding:8px 0;border-bottom:1px solid #222;">
                        <span style="color:rgba(255,255,255,0.4);font-size:13px;">Date</span>
                        <span style="color:#fff;font-size:13px;">{event.date}</span>
                    </div>
                    <div style="display:flex;justify-content:space-between;padding:8px 0;border-bottom:1px solid #222;">
                        <span style="color:rgba(255,255,255,0.4);font-size:13px;">Venue</span>
                        <span style="color:#fff;font-size:13px;">{event.venue}</span>
                    </div>
                    <div style="display:flex;justify-content:space-between;padding:8px 0;border-bottom:1px solid #222;">
                        <span style="color:rgba(255,255,255,0.4);font-size:13px;">Spots</span>
                        <span style="color:#fff;font-size:13px;">{reg.quantity}</span>
                    </div>
                    <div style="display:flex;justify-content:space-between;padding:8px 0;">
                        <span style="color:rgba(255,255,255,0.4);font-size:13px;">Entry Pass ID</span>
                        <span style="color:#f5a623;font-size:13px;font-weight:700;font-family:monospace;">{reg.registration_id}</span>
                    </div>
                </div>
                {static_qr_block}
                <div style="background:rgba(245,166,35,0.08);border:1px solid rgba(245,166,35,0.2);border-radius:12px;padding:14px 16px;margin-bottom:24px;">
                    <div style="color:#f5a623;font-weight:700;font-size:11px;margin-bottom:4px;">🎪 SHOW AT THE GATE</div>
                    <div style="color:rgba(255,255,255,0.5);font-size:12px;">Present this QR code or your entry pass ID to gain entry. Open the Master Events app for a live rotating QR.</div>
                </div>
                <div style="text-align:center;">
                    <a href="{app_url}" style="background:linear-gradient(135deg,#f5a623,#e8920f);color:#fff;padding:14px 40px;border-radius:12px;text-decoration:none;font-weight:700;font-size:15px;display:inline-block;">
                        Open Master Events →
                    </a>
                </div>
            </div>
            <div style="background:#111;border-radius:0 0 20px 20px;border:1px solid #2a2a2a;border-top:none;padding:20px 32px;text-align:center;">
                <p style="color:rgba(255,255,255,0.2);font-size:11px;margin:0;">© 2026 Master Events · masterevents.events</p>
            </div>
        </div>
    </body>
    </html>
    """
    _send_email_async(
        to_email=user.email,
        subject=f"🎟️ You're In — {event.name}",
        html=html,
        text=(
            f"Hi {user.first_name},\n\n"
            f"You're registered for {event.name}!\n\n"
            f"Date: {event.date}\n"
            f"Venue: {event.venue}\n"
            f"Entry Pass ID: {reg.registration_id}\n\n"
            f"Open Master Events to view your QR code: {app_url}"
        ),
    )



def notify_free_registration_with_pdf(reg, qr_b64, pdf_b64=None):
    """
    Free event: send PDF ticket as attachment + QR in email body.
    """
    user    = reg.attendee
    event   = reg.event
    app_url = getattr(settings, 'FRONTEND_URL', 'https://master-events-bi7m.vercel.app')

    qr_block = f"""
    <div style="text-align:center;margin:20px 0;">
        <p style="color:#6b7280;font-size:12px;margin-bottom:8px;">Show this QR code at the entrance</p>
        <img src="data:image/png;base64,{qr_b64}"
             style="width:180px;height:180px;border-radius:10px;background:#fff;padding:8px;border:1px solid #e5e7eb;" />
        <p style="color:#9ca3af;font-size:11px;margin-top:6px;">
            Your PDF ticket is attached · Also in the Master Events app
        </p>
    </div>
    """ if qr_b64 else ""

    html = f"""
    <!DOCTYPE html>
    <html>
    <head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"></head>
    <body style="margin:0;padding:0;background:#f5f5f5;font-family:'Inter','Helvetica Neue',Arial,sans-serif;">
      <div style="max-width:560px;margin:0 auto;padding:24px 16px;">

        <div style="background:linear-gradient(135deg,#16a34a,#15803d);border-radius:16px 16px 0 0;padding:28px 32px;text-align:center;">
          <div style="font-size:32px;margin-bottom:8px;">🎟️</div>
          <h1 style="margin:0;color:#fff;font-size:20px;font-weight:700;">You're Registered!</h1>
          <p style="margin:6px 0 0;color:rgba(255,255,255,0.85);font-size:13px;">{event.name}</p>
        </div>

        <div style="background:#fff;padding:28px 32px;border-left:1px solid #e5e7eb;border-right:1px solid #e5e7eb;">
          <p style="color:#374151;font-size:15px;margin:0 0 18px;">
            Hi <strong>{user.first_name}</strong>, your spot is confirmed — <strong>no charge</strong>!
          </p>

          <div style="background:#f9fafb;border:1px solid #e5e7eb;border-radius:10px;overflow:hidden;margin-bottom:18px;">
            <div style="padding:11px 16px;border-bottom:1px solid #e5e7eb;display:flex;justify-content:space-between;">
              <span style="color:#6b7280;font-size:13px;">Event</span>
              <span style="color:#111;font-size:13px;font-weight:600;">{event.name}</span>
            </div>
            <div style="padding:11px 16px;border-bottom:1px solid #e5e7eb;display:flex;justify-content:space-between;">
              <span style="color:#6b7280;font-size:13px;">Date</span>
              <span style="color:#111;font-size:13px;">{event.date}</span>
            </div>
            <div style="padding:11px 16px;border-bottom:1px solid #e5e7eb;display:flex;justify-content:space-between;">
              <span style="color:#6b7280;font-size:13px;">Venue</span>
              <span style="color:#111;font-size:13px;">{event.venue}</span>
            </div>
            <div style="padding:11px 16px;border-bottom:1px solid #e5e7eb;display:flex;justify-content:space-between;">
              <span style="color:#6b7280;font-size:13px;">Spots</span>
              <span style="color:#111;font-size:13px;">{reg.quantity}</span>
            </div>
            <div style="padding:11px 16px;display:flex;justify-content:space-between;">
              <span style="color:#6b7280;font-size:13px;">Entry Pass ID</span>
              <span style="color:#16a34a;font-size:13px;font-weight:700;font-family:monospace;">{reg.registration_id}</span>
            </div>
          </div>

          {qr_block}

          {"<div style='background:#dcfce7;border:1px solid #bbf7d0;border-radius:10px;padding:12px 16px;margin-bottom:16px;font-size:12px;color:#15803d;'><strong>📎 Your PDF ticket is attached</strong> — print it or save it as a backup entry pass.</div>" if pdf_b64 else ""}

          <div style="background:#fef3c7;border:1px solid #fde68a;border-radius:10px;padding:12px 16px;margin-bottom:20px;">
            <div style="font-weight:700;font-size:12px;color:#92400e;margin-bottom:3px;">🎪 AT THE GATE</div>
            <div style="font-size:12px;color:#78350f;line-height:1.6;">
              Show the QR code (from this email or the app) to the door staff for instant entry.
            </div>
          </div>

          <div style="text-align:center;">
            <a href="{app_url}" style="background:linear-gradient(135deg,#16a34a,#15803d);color:#fff;padding:13px 36px;border-radius:10px;text-decoration:none;font-weight:600;font-size:14px;display:inline-block;">
              Open in App →
            </a>
          </div>
        </div>

        <div style="background:#f9fafb;border-radius:0 0 16px 16px;border:1px solid #e5e7eb;border-top:none;padding:16px 32px;text-align:center;">
          <p style="color:#9ca3af;font-size:11px;margin:0;">© 2026 Master Events · masterevents.events</p>
        </div>
      </div>
    </body>
    </html>
    """

    def _send():
        try:
            resend.api_key = settings.RESEND_API_KEY
            params = {
                "from":    settings.DEFAULT_FROM_EMAIL,
                "to":      [user.email],
                "subject": f"🎟️ Your Free Ticket — {event.name}",
                "html":    html,
                "text": (
                    f"Hi {user.first_name},\n\n"
                    f"You're registered for {event.name}!\n\n"
                    f"Date: {event.date}\n"
                    f"Venue: {event.venue}\n"
                    f"Entry Pass ID: {reg.registration_id}\n\n"
                    f"Your PDF ticket is attached.\n"
                    f"Open Master Events app: {app_url}"
                ),
            }
            # Attach PDF if generated
            if pdf_b64:
                import base64
                params["attachments"] = [{
                    "filename": f"ticket-{reg.registration_id}.pdf",
                    "content":  pdf_b64,
                }]
            r = resend.Emails.send(params)
            print(f"✅ PDF ticket email sent: {r}")
        except Exception as e:
            print(f"❌ PDF ticket email error: {e}")

    import threading
    threading.Thread(target=_send, daemon=True).start()