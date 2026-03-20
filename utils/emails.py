from django.core.mail import send_mail
from django.conf import settings
from accounts.models import Notification

def send_notification(user, type, title, body, send_email=True):
    """Create in-app notification and optionally send email"""
    
    # Create in-app notification
    Notification.objects.create(
        user=user,
        type=type,
        title=title,
        body=body,
    )
    
    # Send email
    if send_email:
        try:
            send_mail(
                subject=f"Master Events — {title}",
                message=body,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                html_message=f"""
                <div style="font-family: sans-serif; max-width: 600px; margin: 0 auto; background: #1a0e00; color: #fff; border-radius: 16px; overflow: hidden;">
                    <div style="background: linear-gradient(135deg, #f5a623, #e8920f); padding: 32px; text-align: center;">
                        <h1 style="margin: 0; font-size: 28px;">🎟️ Master Events</h1>
                        <p style="margin: 8px 0 0; opacity: 0.85; font-size: 13px; letter-spacing: 2px;">IF NOT NOW, WHEN?</p>
                    </div>
                    <div style="padding: 32px;">
                        <h2 style="color: #f5a623; margin: 0 0 16px;">{title}</h2>
                        <p style="color: rgba(255,255,255,0.8); line-height: 1.7; margin: 0 0 24px;">{body}</p>
                        <div style="background: rgba(245,166,35,0.1); border: 1px solid rgba(245,166,35,0.3); border-radius: 12px; padding: 16px; text-align: center;">
                            <p style="margin: 0; color: rgba(255,255,255,0.5); font-size: 12px;">Master Events Ghana · Your Premier Ticketing Platform</p>
                        </div>
                    </div>
                </div>
                """,
                fail_silently=True,
            )
        except Exception as e:
            print(f"Email error: {e}")

def notify_ticket_purchase(ticket):
    user = ticket.owner
    event = ticket.event
    send_notification(
        user=user,
        type='purchase',
        title='Ticket Purchase Confirmed! 🎟️',
        body=f'Your {ticket.quantity} ticket(s) for {event.name} on {event.date} at {event.venue} have been confirmed. Total paid: Ghc {ticket.price_paid}. Your QR code is ready — show it at the door.',
    )
    # Notify organizer
    send_notification(
        user=event.organizer,
        type='sale',
        title=f'New Sale — {event.name} 💰',
        body=f'{user.full_name} just purchased {ticket.quantity} ticket(s) for {event.name}. Ghc {float(ticket.price_paid) * 0.95:.2f} has been added to your wallet.',
    )

def notify_ticket_transfer(ticket, from_user, to_user):
    send_notification(
        user=from_user,
        type='transfer_sent',
        title='Ticket Transferred ✅',
        body=f'Your ticket for {ticket.event.name} has been successfully transferred to {to_user.full_name} ({to_user.email}). Your old QR code is now void.',
    )
    send_notification(
        user=to_user,
        type='transfer_received',
        title='You Received a Ticket! 🎟️',
        body=f'{from_user.full_name} transferred a ticket for {ticket.event.name} on {ticket.event.date} at {ticket.event.venue} to you. Check your tickets to view your QR code.',
    )

def notify_resale_listed(ticket, user):
    send_notification(
        user=user,
        type='resale_listed',
        title='Ticket Listed for Resale 🏷️',
        body=f'Your ticket for {ticket.event.name} has been listed on the resale market at Ghc {ticket.resale_price}. You will be notified when it sells.',
    )

def notify_withdrawal(wallet, amount, method, reference):
    send_notification(
        user=wallet.user,
        type='withdrawal',
        title='Withdrawal Initiated 💸',
        body=f'Your withdrawal of Ghc {amount} via {method} has been initiated. Reference: {reference}. Funds will arrive within 5-10 minutes.',
    )