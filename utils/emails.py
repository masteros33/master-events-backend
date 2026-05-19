from django.core.mail import send_mail
from django.conf import settings
from accounts.models import Notification
import threading


def _send_email_async(subject, message, from_email, recipient_list, html_message):
    """Send email in background thread — never blocks the request"""
    def _send():
        try:
            send_mail(
                subject=subject,
                message=message,
                from_email=from_email,
                recipient_list=recipient_list,
                html_message=html_message,
                fail_silently=True,
            )
        except Exception as e:
            print(f"Async email error: {e}")
    thread = threading.Thread(target=_send, daemon=True)
    thread.start()


def send_notification(user, type, title, body, send_email=True, action_url=None):
    """Create in-app notification and optionally send email"""

    # Create in-app notification
    Notification.objects.create(
        user=user,
        type=type,
        title=title,
        body=body,
    )

    if send_email:
        try:
            action_button = ""
            if action_url:
                action_button = f"""
                <div style="text-align: center; margin: 24px 0;">
                    <a href="{action_url}" style="background: linear-gradient(135deg, #f5a623, #e8920f); color: #fff; padding: 14px 32px; border-radius: 12px; text-decoration: none; font-weight: 700; font-size: 15px; display: inline-block;">
                        View Ticket →
                    </a>
                </div>
                """

            html_message = f"""
            <!DOCTYPE html>
            <html>
            <head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
            <body style="margin: 0; padding: 0; background: #0f0f0f; font-family: 'Helvetica Neue', Arial, sans-serif;">
                <div style="max-width: 600px; margin: 0 auto; padding: 24px 16px;">
                    <div style="background: linear-gradient(135deg, #f5a623, #e8920f); border-radius: 20px 20px 0 0; padding: 32px; text-align: center;">
                        <div style="font-size: 32px; margin-bottom: 8px;">🎟️</div>
                        <h1 style="margin: 0; color: #fff; font-size: 24px; font-weight: 900; letter-spacing: -0.5px;">Master Events</h1>
                        <p style="margin: 6px 0 0; color: rgba(255,255,255,0.8); font-size: 12px; letter-spacing: 2px; text-transform: uppercase;">Ghana's NFT Ticketing Platform</p>
                    </div>
                    <div style="background: #1a1a1a; padding: 32px; border-left: 1px solid #2a2a2a; border-right: 1px solid #2a2a2a;">
                        <h2 style="color: #f5a623; margin: 0 0 16px; font-size: 20px; font-weight: 800;">{title}</h2>
                        <p style="color: rgba(255,255,255,0.75); line-height: 1.8; margin: 0 0 20px; font-size: 15px; white-space: pre-line;">{body}</p>
                        {action_button}
                        <div style="background: rgba(124,58,237,0.1); border: 1px solid rgba(124,58,237,0.25); border-radius: 12px; padding: 14px 16px; margin-top: 24px;">
                            <div style="display: flex; align-items: center; gap: 10px;">
                                <span style="font-size: 18px;">⛓️</span>
                                <div>
                                    <div style="color: #a78bfa; font-weight: 700; font-size: 11px; letter-spacing: 0.5px;">SECURED BY POLYGON BLOCKCHAIN</div>
                                    <div style="color: rgba(255,255,255,0.4); font-size: 11px; margin-top: 2px;">All tickets are NFTs — impossible to fake or duplicate</div>
                                </div>
                            </div>
                        </div>
                    </div>
                    <div style="background: #111; border-radius: 0 0 20px 20px; border: 1px solid #2a2a2a; border-top: none; padding: 20px 32px; text-align: center;">
                        <p style="color: rgba(255,255,255,0.25); font-size: 11px; margin: 0 0 6px;">© 2026 Master Events Ghana · Built on Polygon</p>
                        <p style="color: rgba(255,255,255,0.15); font-size: 10px; margin: 0;">You received this email because you have an account on Master Events.</p>
                    </div>
                </div>
            </body>
            </html>
            """

            _send_email_async(
                subject=f"Master Events — {title}",
                message=body,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                html_message=html_message,
            )
        except Exception as e:
            print(f"Email setup error: {e}")


def notify_ticket_purchase(ticket):
    user  = ticket.owner
    event = ticket.event
    app_url = getattr(settings, 'FRONTEND_URL', 'https://master-events-bi7m.vercel.app')

    send_notification(
        user=user,
        type='purchase',
        title='Ticket Purchase Confirmed! 🎟️',
        body=(
            f"Hi {user.first_name},\n\n"
            f"Your {ticket.quantity} ticket(s) for {event.name} have been confirmed.\n\n"
            f"📅 Date: {event.date}\n"
            f"📍 Venue: {event.venue}\n"
            f"💰 Total paid: GHS {ticket.price_paid}\n"
            f"🎟️ Ticket ID: {ticket.ticket_id}\n\n"
            f"Your QR code is ready — show it at the door. "
            f"It refreshes every 10 seconds and is screenshot-proof.\n\n"
            f"Your ticket is being minted as an NFT on the Polygon blockchain."
        ),
        action_url=app_url,
    )

    send_notification(
        user=event.organizer,
        type='sale',
        title=f'New Sale — {event.name} 💰',
        body=(
            f"Hi {event.organizer.first_name},\n\n"
            f"{user.get_full_name() or user.email} just purchased "
            f"{ticket.quantity} ticket(s) for {event.name}.\n\n"
            f"💰 GHS {float(ticket.price_paid) * 0.95:.2f} has been added to your wallet.\n"
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
            f"Your ticket for {ticket.event.name} has been successfully transferred to "
            f"{to_user.get_full_name() or to_user.email}.\n\n"
            f"Your old QR code is now void and can no longer be used for entry."
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
            f"Log in to Master Events to view your QR code and ticket details."
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
            f"Your ticket for {ticket.event.name} has been listed on the resale market "
            f"at GHS {ticket.resale_price}.\n\n"
            f"You will be notified when it sells. Only 2% platform fee — you keep 98%."
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
            f"⏱️ Funds will arrive within 5-10 minutes."
        ),
    )


def notify_password_reset(user, reset_url):
    """Send password reset email — async so it never blocks"""
    try:
        html_message = f"""
        <!DOCTYPE html>
        <html>
        <head><meta charset="UTF-8"></head>
        <body style="margin: 0; padding: 0; background: #0f0f0f; font-family: Arial, sans-serif;">
            <div style="max-width: 600px; margin: 0 auto; padding: 24px 16px;">
                <div style="background: linear-gradient(135deg, #f5a623, #e8920f); border-radius: 20px 20px 0 0; padding: 32px; text-align: center;">
                    <div style="font-size: 32px; margin-bottom: 8px;">🔐</div>
                    <h1 style="margin: 0; color: #fff; font-size: 22px; font-weight: 900;">Reset Your Password</h1>
                    <p style="margin: 6px 0 0; color: rgba(255,255,255,0.8); font-size: 12px;">Master Events Ghana</p>
                </div>
                <div style="background: #1a1a1a; padding: 32px; border: 1px solid #2a2a2a; border-top: none;">
                    <p style="color: rgba(255,255,255,0.75); font-size: 15px; line-height: 1.8; margin: 0 0 24px;">
                        Hi {user.first_name},<br><br>
                        We received a request to reset your Master Events password.
                        Click the button below — this link expires in
                        <strong style="color: #f5a623;">30 minutes</strong>.
                    </p>
                    <div style="text-align: center; margin: 28px 0;">
                        <a href="{reset_url}"
                           style="background: linear-gradient(135deg, #f5a623, #e8920f); color: #fff; padding: 16px 40px; border-radius: 12px; text-decoration: none; font-weight: 700; font-size: 16px; display: inline-block;">
                            Reset Password →
                        </a>
                    </div>
                    <p style="color: rgba(255,255,255,0.35); font-size: 12px; line-height: 1.6; margin: 0;">
                        If you didn't request this, you can safely ignore this email.
                        Your password will not change.<br><br>
                        For security, this link expires in 30 minutes.
                    </p>
                </div>
                <div style="background: #111; border-radius: 0 0 20px 20px; border: 1px solid #2a2a2a; border-top: none; padding: 16px; text-align: center;">
                    <p style="color: rgba(255,255,255,0.2); font-size: 10px; margin: 0;">© 2026 Master Events Ghana</p>
                </div>
            </div>
        </body>
        </html>
        """

        _send_email_async(
            subject="Master Events — Reset Your Password",
            message=(
                f"Hi {user.first_name},\n\n"
                f"Click this link to reset your password (expires in 30 minutes):\n"
                f"{reset_url}\n\n"
                f"If you didn't request this, ignore this email."
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            html_message=html_message,
        )
        return True
    except Exception as e:
        print(f"Password reset email error: {e}")
        return False