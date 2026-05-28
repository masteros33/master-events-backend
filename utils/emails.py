import resend
import threading
from django.conf import settings
from accounts.models import Notification


def _send_email_async(to_email, subject, html, text):
    """Send email via Resend API in background thread"""
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


def _build_html(title, body, action_url=None):
    action_button = ""
    if action_url:
        action_button = f"""
        <div style="text-align:center;margin:24px 0;">
            <a href="{action_url}"
               style="background:linear-gradient(135deg,#f5a623,#e8920f);color:#fff;padding:14px 32px;border-radius:12px;text-decoration:none;font-weight:700;font-size:15px;display:inline-block;">
                View Ticket →
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
                <div style="font-size:32px;margin-bottom:8px;">🎟️</div>
                <h1 style="margin:0;color:#fff;font-size:24px;font-weight:900;letter-spacing:-0.5px;">Master Events</h1>
                <p style="margin:6px 0 0;color:rgba(255,255,255,0.8);font-size:12px;letter-spacing:2px;text-transform:uppercase;">Ghana's NFT Ticketing Platform</p>
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
                <p style="color:rgba(255,255,255,0.25);font-size:11px;margin:0 0 4px;">© 2026 Master Events Ghana · Built on Polygon</p>
                <p style="color:rgba(255,255,255,0.15);font-size:10px;margin:0;">You received this because you have a Master Events account.</p>
            </div>
        </div>
    </body>
    </html>
    """


def send_notification(user, type, title, body, send_email=True, action_url=None):
    """Create in-app notification and optionally send email via Resend"""
    Notification.objects.create(user=user, type=type, title=title, body=body)

    if send_email and user.email:
        html = _build_html(title, body, action_url)
        _send_email_async(
            to_email=user.email,
            subject=f"Master Events — {title}",
            html=html,
            text=body,
        )


def notify_welcome(user):
    """Send welcome email to new user"""
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
                <p style="margin:8px 0 0;color:rgba(255,255,255,0.85);font-size:14px;">Ghana's NFT-powered ticketing platform</p>
            </div>

            <div style="background:#1a1a1a;padding:32px;border-left:1px solid #2a2a2a;border-right:1px solid #2a2a2a;">
                <p style="color:rgba(255,255,255,0.85);font-size:16px;line-height:1.7;margin:0 0 24px;">
                    Hi <strong style="color:#fff;">{user.first_name}</strong> 👋,<br><br>
                    You're now part of Master Events — where every ticket is an NFT on the Polygon blockchain.
                    No fakes. No scalping. Just real tickets, owned by you.
                </p>

                <div style="background:#111;border:1px solid #2a2a2a;border-radius:14px;padding:20px;margin-bottom:24px;">
                    <div style="font-size:11px;font-weight:700;color:#f5a623;letter-spacing:1.5px;margin-bottom:14px;">WHAT YOU CAN DO</div>
                    {chr(10).join([f'''
                    <div style="display:flex;align-items:flex-start;gap:12px;margin-bottom:14px;">
                        <div style="width:32px;height:32px;border-radius:8px;background:rgba(245,166,35,0.1);display:flex;align-items:center;justify-content:center;font-size:16px;flex-shrink:0;">{icon}</div>
                        <div>
                            <div style="font-weight:700;font-size:13px;color:#fff;margin-bottom:2px;">{title}</div>
                            <div style="font-size:12px;color:rgba(255,255,255,0.45);">{sub}</div>
                        </div>
                    </div>''' for icon, title, sub in [
                        ("🎫", "Buy Tickets", "Browse events across Ghana and buy with MoMo or card"),
                        ("⛓️", "Own as NFT", "Every ticket is minted on Polygon — verifiable forever"),
                        ("🔄", "Resell Safely", "List tickets on our marketplace at fair prices"),
                        ("📱", "Screenshot-proof QR", "Your QR refreshes every 10 seconds — impossible to fake"),
                    ]])}
                </div>

                <div style="text-align:center;margin-bottom:20px;">
                    <a href="{app_url}"
                       style="background:linear-gradient(135deg,#f5a623,#e8920f);color:#fff;padding:16px 48px;border-radius:14px;text-decoration:none;font-weight:700;font-size:16px;display:inline-block;box-shadow:0 4px 20px rgba(245,166,35,0.35);">
                        Browse Events →
                    </a>
                </div>

                <div style="background:rgba(124,58,237,0.08);border:1px solid rgba(124,58,237,0.2);border-radius:12px;padding:14px 16px;text-align:center;">
                    <span style="font-size:14px;">⛓️</span>
                    <span style="color:#a78bfa;font-weight:700;font-size:11px;letter-spacing:0.5px;margin-left:6px;">POWERED BY POLYGON BLOCKCHAIN</span>
                    <div style="color:rgba(255,255,255,0.35);font-size:11px;margin-top:4px;">All tickets are NFTs — impossible to fake or duplicate</div>
                </div>
            </div>

            <div style="background:#111;border-radius:0 0 20px 20px;border:1px solid #2a2a2a;border-top:none;padding:20px 32px;text-align:center;">
                <p style="color:rgba(255,255,255,0.2);font-size:11px;margin:0 0 4px;">© 2026 Master Events Ghana · Built on Polygon</p>
                <p style="color:rgba(255,255,255,0.12);font-size:10px;margin:0;">You received this because you just created a Master Events account.</p>
            </div>
        </div>
    </body>
    </html>
    """
    _send_email_async(
        to_email=user.email,
        subject="Welcome to Master Events! 🎟️",
        html=html,
        text=(
            f"Hi {user.first_name},\n\n"
            f"Welcome to Master Events Ghana!\n\n"
            f"Every ticket is an NFT on Polygon — no fakes, no scalping.\n\n"
            f"Browse events: {app_url}\n\n"
            f"— Master Events Team"
        ),
    )


def notify_ticket_purchase(ticket):
    user        = ticket.owner
    event       = ticket.event
    app_url     = getattr(settings, 'FRONTEND_URL', 'https://master-events-bi7m.vercel.app')
    event_image = getattr(event, 'image', '') or ''

    image_block = f"""
    <div style="border-radius:14px;overflow:hidden;margin-bottom:20px;">
        <img src="{event_image}" alt="{event.name}"
             style="width:100%;height:200px;object-fit:cover;display:block;"/>
        <div style="background:linear-gradient(135deg,#1a1a1a,#0f0f0f);padding:16px;">
            <div style="font-size:18px;font-weight:800;color:#fff;margin-bottom:4px;">{event.name}</div>
            <div style="font-size:13px;color:rgba(255,255,255,0.55);">📅 {event.date} &nbsp;·&nbsp; 📍 {event.venue}</div>
        </div>
    </div>
    """ if event_image else f"""
    <div style="background:linear-gradient(135deg,#1a0533,#0d1b4b);border-radius:14px;padding:24px;margin-bottom:20px;text-align:center;">
        <div style="font-size:32px;margin-bottom:8px;">🎟️</div>
        <div style="font-size:18px;font-weight:800;color:#fff;margin-bottom:4px;">{event.name}</div>
        <div style="font-size:13px;color:rgba(255,255,255,0.55);">📅 {event.date} &nbsp;·&nbsp; 📍 {event.venue}</div>
    </div>
    """

    html = f"""
    <!DOCTYPE html>
    <html>
    <head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"></head>
    <body style="margin:0;padding:0;background:#0f0f0f;font-family:'Helvetica Neue',Arial,sans-serif;">
        <div style="max-width:600px;margin:0 auto;padding:24px 16px;">

            <div style="background:linear-gradient(135deg,#f5a623,#e8920f);border-radius:20px 20px 0 0;padding:28px 32px;text-align:center;">
                <div style="font-size:36px;margin-bottom:8px;">🎟️</div>
                <h1 style="margin:0;color:#fff;font-size:22px;font-weight:900;">Ticket Confirmed!</h1>
                <p style="margin:6px 0 0;color:rgba(255,255,255,0.85);font-size:13px;">Your NFT ticket is ready</p>
            </div>

            <div style="background:#1a1a1a;padding:28px 32px;border-left:1px solid #2a2a2a;border-right:1px solid #2a2a2a;">
                <p style="color:rgba(255,255,255,0.8);font-size:15px;margin:0 0 20px;">
                    Hi <strong style="color:#fff;">{user.first_name}</strong>, your payment was successful!
                </p>

                {image_block}

                <div style="background:#111;border:1px solid #2a2a2a;border-radius:14px;padding:18px;margin-bottom:20px;">
                    <div style="display:flex;justify-content:space-between;padding:8px 0;border-bottom:1px solid #222;">
                        <span style="color:rgba(255,255,255,0.4);font-size:13px;">Ticket ID</span>
                        <span style="color:#f5a623;font-size:13px;font-weight:700;font-family:monospace;">{ticket.ticket_id}</span>
                    </div>
                    <div style="display:flex;justify-content:space-between;padding:8px 0;border-bottom:1px solid #222;">
                        <span style="color:rgba(255,255,255,0.4);font-size:13px;">Quantity</span>
                        <span style="color:#fff;font-size:13px;font-weight:600;">{ticket.quantity} ticket(s)</span>
                    </div>
                    <div style="display:flex;justify-content:space-between;padding:8px 0;border-bottom:1px solid #222;">
                        <span style="color:rgba(255,255,255,0.4);font-size:13px;">Amount Paid</span>
                        <span style="color:#fff;font-size:13px;font-weight:600;">GHS {ticket.price_paid}</span>
                    </div>
                    <div style="display:flex;justify-content:space-between;padding:8px 0;">
                        <span style="color:rgba(255,255,255,0.4);font-size:13px;">Date</span>
                        <span style="color:#fff;font-size:13px;font-weight:600;">{event.date}</span>
                    </div>
                </div>

                <div style="background:rgba(124,58,237,0.1);border:1px solid rgba(124,58,237,0.25);border-radius:12px;padding:14px 16px;margin-bottom:24px;">
                    <div style="color:#a78bfa;font-weight:700;font-size:11px;letter-spacing:0.5px;margin-bottom:4px;">⛓️ NFT MINTING ON POLYGON</div>
                    <div style="color:rgba(255,255,255,0.5);font-size:12px;">Your ticket is being minted as an NFT. It will appear in your wallet shortly.</div>
                </div>

                <div style="text-align:center;">
                    <a href="{app_url}"
                       style="background:linear-gradient(135deg,#f5a623,#e8920f);color:#fff;padding:14px 40px;border-radius:12px;text-decoration:none;font-weight:700;font-size:15px;display:inline-block;">
                        View My Ticket →
                    </a>
                </div>

                <p style="color:rgba(255,255,255,0.3);font-size:12px;text-align:center;margin-top:20px;">
                    Show your QR code at the gate — it refreshes every 10 seconds and is screenshot-proof.
                </p>
            </div>

            <div style="background:#111;border-radius:0 0 20px 20px;border:1px solid #2a2a2a;border-top:none;padding:20px 32px;text-align:center;">
                <p style="color:rgba(255,255,255,0.2);font-size:11px;margin:0;">© 2026 Master Events Ghana · Built on Polygon</p>
            </div>
        </div>
    </body>
    </html>
    """

    _send_email_async(
        to_email=user.email,
        subject=f"🎟️ Ticket Confirmed — {event.name}",
        html=html,
        text=(
            f"Hi {user.first_name},\n\n"
            f"Your ticket for {event.name} is confirmed!\n\n"
            f"Ticket ID: {ticket.ticket_id}\n"
            f"Quantity: {ticket.quantity}\n"
            f"Amount: GHS {ticket.price_paid}\n"
            f"Date: {event.date}\n"
            f"Venue: {event.venue}\n\n"
            f"Open the app to view your QR code: {app_url}"
        ),
    )

    # Notify organizer in-app only
    send_notification(
        user=event.organizer,
        type='sale',
        title=f'New Sale — {event.name} 💰',
        body=(
            f"Hi {event.organizer.first_name},\n\n"
            f"{user.get_full_name() or user.email} just purchased "
            f"{ticket.quantity} ticket(s) for {event.name}.\n\n"
            f"💰 GHS {float(ticket.price_paid) * 0.95:.2f} added to your wallet.\n"
            f"🎟️ Ticket ID: {ticket.ticket_id}"
        ),
        send_email=False,
    )


def notify_ticket_transfer(ticket, from_user, to_user):
    send_notification(
        user=from_user,
        type='transfer_sent',
        title='Ticket Transferred ✅',
        body=(
            f"Hi {from_user.first_name},\n\n"
            f"Your ticket for {ticket.event.name} has been transferred to "
            f"{to_user.get_full_name() or to_user.email}.\n\n"
            f"Your old QR code is now void."
        ),
    )
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
            f"Log in to Master Events to view your QR code."
        ),
        action_url=getattr(settings, 'FRONTEND_URL', 'https://master-events-bi7m.vercel.app'),
    )


def notify_resale_listed(ticket, user):
    send_notification(
        user=user,
        type='resale_listed',
        title='Ticket Listed for Resale 🏷️',
        body=(
            f"Hi {user.first_name},\n\n"
            f"Your ticket for {ticket.event.name} has been listed at GHS {ticket.resale_price}.\n\n"
            f"You'll be notified when it sells. Only 2% platform fee."
        ),
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
    )


def notify_password_reset(user, reset_url):
    """Send password reset email via Resend"""
    html = f"""
    <!DOCTYPE html>
    <html>
    <head><meta charset="UTF-8"></head>
    <body style="margin:0;padding:0;background:#0f0f0f;font-family:Arial,sans-serif;">
        <div style="max-width:600px;margin:0 auto;padding:24px 16px;">
            <div style="background:linear-gradient(135deg,#f5a623,#e8920f);border-radius:20px 20px 0 0;padding:32px;text-align:center;">
                <div style="font-size:32px;margin-bottom:8px;">🔐</div>
                <h1 style="margin:0;color:#fff;font-size:22px;font-weight:900;">Reset Your Password</h1>
                <p style="margin:6px 0 0;color:rgba(255,255,255,0.8);font-size:12px;">Master Events Ghana</p>
            </div>
            <div style="background:#1a1a1a;padding:32px;border:1px solid #2a2a2a;border-top:none;">
                <p style="color:rgba(255,255,255,0.75);font-size:15px;line-height:1.8;margin:0 0 24px;">
                    Hi {user.first_name},<br><br>
                    We received a request to reset your Master Events password.
                    Click below — this link expires in <strong style="color:#f5a623;">30 minutes</strong>.
                </p>
                <div style="text-align:center;margin:28px 0;">
                    <a href="{reset_url}"
                       style="background:linear-gradient(135deg,#f5a623,#e8920f);color:#fff;padding:16px 40px;border-radius:12px;text-decoration:none;font-weight:700;font-size:16px;display:inline-block;">
                        Reset Password →
                    </a>
                </div>
                <p style="color:rgba(255,255,255,0.35);font-size:12px;line-height:1.6;margin:0;">
                    If you didn't request this, ignore this email. Your password won't change.
                </p>
            </div>
            <div style="background:#111;border-radius:0 0 20px 20px;border:1px solid #2a2a2a;border-top:none;padding:16px;text-align:center;">
                <p style="color:rgba(255,255,255,0.2);font-size:10px;margin:0;">© 2026 Master Events Ghana</p>
            </div>
        </div>
    </body>
    </html>
    """
    _send_email_async(
        to_email=user.email,
        subject="Master Events — Reset Your Password",
        html=html,
        text=(
            f"Hi {user.first_name},\n\n"
            f"Reset your password here (expires in 30 minutes):\n{reset_url}\n\n"
            f"If you didn't request this, ignore this email."
        ),
    )
    return True