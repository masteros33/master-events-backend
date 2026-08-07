import resend
import threading
from django.conf import settings
from accounts.models import Notification

# ═══════════════════════════════════════════════════════════════
#  DESIGN SYSTEM — shared components so every email looks
#  consistent. Colors match the brand orange used across the app.
# ═══════════════════════════════════════════════════════════════

BRAND_GRADIENT = "linear-gradient(135deg,#f5a623,#e8920f)"
BG_OUTER  = "#0a0a0c"
BG_PANEL  = "#141416"
BG_CARD   = "#0f0f11"
BORDER    = "rgba(245,166,35,0.15)"
FONT      = "'Helvetica Neue',Arial,sans-serif"

PILL_COLORS = {
    "green":  ("#22c55e", "rgba(34,197,94,0.12)",  "#22c55e"),
    "orange": ("#f5a623", "rgba(245,166,35,0.12)", "#f5a623"),
    "red":    ("#ef4444", "rgba(239,68,68,0.12)",  "#ef4444"),
}
NOTICE_COLORS = {
    "orange": ("rgba(245,166,35,0.06)", "rgba(245,166,35,0.18)", "#f5a623"),
    "purple": ("rgba(124,58,237,0.06)", "rgba(124,58,237,0.18)", "#a78bfa"),
    "green":  ("rgba(34,197,94,0.06)",  "rgba(34,197,94,0.18)",  "#4ade80"),
    "amber":  ("rgba(251,191,36,0.08)", "rgba(251,191,36,0.2)",  "#fbbf24"),
    "red":    ("rgba(239,68,68,0.06)",  "rgba(239,68,68,0.18)",  "#f87171"),
}


def _send_email_async(to_email, subject, html, text, attachments=None):
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
            if attachments:
                params["attachments"] = attachments
            r = resend.Emails.send(params)
            print(f"✅ Email sent via Resend: {r}")
        except Exception as e:
            print(f"❌ Resend email error: {e}")
    threading.Thread(target=_send, daemon=True).start()


def _upload_base64_qr(base64_str, public_id):
    """
    Upload a base64 QR image to Cloudinary and return a real hosted
    URL. Data-URI images (data:image/png;base64,...) are silently
    stripped by many mail clients — this is what caused blank QR
    boxes in delivered emails. A hosted https:// URL renders
    reliably everywhere. Falls back to the base64 data URI only if
    the upload itself fails, so nothing regresses if Cloudinary is
    briefly unavailable.
    """
    if not base64_str:
        return None
    try:
        import cloudinary.uploader
        result = cloudinary.uploader.upload(
            f"data:image/png;base64,{base64_str}",
            folder="master_events/qr_codes",
            public_id=public_id,
            resource_type="image",
            overwrite=True,
        )
        return result.get('secure_url')
    except Exception as e:
        print(f"⚠️ QR Cloudinary upload failed, falling back to inline: {e}")
        return f"data:image/png;base64,{base64_str}"


# ── Shared components ───────────────────────────────────────

def _shell(inner_html):
    return f"""
    <!DOCTYPE html>
    <html>
    <head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"></head>
    <body style="margin:0;padding:0;background:{BG_OUTER};font-family:{FONT};">
        <div style="max-width:560px;margin:0 auto;padding:32px 16px;">
            {inner_html}
        </div>
    </body>
    </html>
    """


def _pill(label, color="green"):
    dot, bg, text = PILL_COLORS.get(color, PILL_COLORS["green"])
    return f"""
    <div style="display:inline-flex;align-items:center;gap:6px;background:{bg};border:1px solid {text}4d;border-radius:999px;padding:5px 14px;margin-bottom:18px;">
        <span style="width:6px;height:6px;border-radius:50%;background:{dot};display:inline-block;"></span>
        <span style="color:{text};font-size:10px;font-weight:700;letter-spacing:1.5px;">{label}</span>
    </div>
    """


def _header(icon, title, subtitle, pill_label=None, pill_color="green"):
    pill = _pill(pill_label, pill_color) if pill_label else ""
    return f"""
    <div style="background:linear-gradient(160deg,#1a1a1e 0%,#0f0f11 100%);border:1px solid {BORDER};border-radius:20px 20px 0 0;padding:36px 32px 30px;text-align:center;">
        <div style="font-size:34px;margin-bottom:14px;">{icon}</div>
        {pill}
        <h1 style="margin:0 0 8px;color:#fff;font-size:23px;font-weight:800;letter-spacing:-0.4px;">{title}</h1>
        <p style="margin:0;color:rgba(255,255,255,0.5);font-size:13px;">{subtitle}</p>
    </div>
    """


def _footer():
    return f"""
    <div style="background:{BG_OUTER};border-radius:0 0 20px 20px;border:1px solid {BORDER};border-top:none;padding:18px 32px;text-align:center;">
        <p style="color:rgba(255,255,255,0.2);font-size:10px;margin:0;">© 2026 Master Events · masterevents.events</p>
    </div>
    """


def _cta_button(url, label):
    return f"""
    <div style="text-align:center;">
        <a href="{url}" style="background:{BRAND_GRADIENT};color:#fff;padding:14px 40px;border-radius:12px;text-decoration:none;font-weight:700;font-size:14px;display:inline-block;">
            {label}
        </a>
    </div>
    """


def _detail_card(rows):
    """rows: list of (label, value, accent_color_or_None)"""
    items = "".join([
        f'''<div style="display:flex;justify-content:space-between;align-items:center;padding:13px 18px;{"border-bottom:1px solid rgba(255,255,255,0.06);" if i < len(rows) - 1 else ""}">
            <span style="color:rgba(255,255,255,0.35);font-size:11px;font-weight:600;letter-spacing:0.5px;text-transform:uppercase;">{label}</span>
            <span style="color:{accent or '#fff'};font-size:13px;font-weight:{700 if accent else 500};font-family:{"'SF Mono',Consolas,monospace" if accent else "inherit"};text-align:right;max-width:60%;">{value}</span>
        </div>'''
        for i, (label, value, accent) in enumerate(rows)
    ])
    return f"""
    <div style="background:{BG_CARD};border:1px solid rgba(255,255,255,0.08);border-radius:16px;padding:4px;margin-bottom:24px;">
        <div style="border-radius:12px;overflow:hidden;">{items}</div>
    </div>
    """


def _notice(scheme, title, body):
    bg, border, text = NOTICE_COLORS.get(scheme, NOTICE_COLORS["orange"])
    return f"""
    <div style="background:{bg};border:1px solid {border};border-radius:12px;padding:14px 16px;margin-bottom:20px;">
        <div style="color:{text};font-weight:700;font-size:11px;letter-spacing:0.5px;margin-bottom:4px;">{title}</div>
        <div style="color:rgba(255,255,255,0.5);font-size:12px;line-height:1.6;">{body}</div>
    </div>
    """


def _qr_card(qr_src, caption="Show at Entrance"):
    if not qr_src:
        return ""
    return f"""
    <div style="text-align:center;margin-bottom:24px;">
        <p style="color:rgba(255,255,255,0.4);font-size:11px;font-weight:700;letter-spacing:1.5px;text-transform:uppercase;margin:0 0 14px;">{caption}</p>
        <div style="display:inline-block;padding:14px;background:#fff;border-radius:16px;box-shadow:0 0 0 1px rgba(245,166,35,0.3),0 0 24px rgba(245,166,35,0.15);">
            <img src="{qr_src}" width="176" height="176" alt="QR Code" style="display:block;width:176px;height:176px;border-radius:8px;" />
        </div>
    </div>
    """


def _panel(body_inner):
    return f"""<div style="background:{BG_PANEL};padding:30px 32px;border-left:1px solid {BORDER};border-right:1px solid {BORDER};">{body_inner}</div>"""


# ── Generic notification builder — used by send_notification() ──
def _build_html(title, body, action_url=None, action_label="View →", icon="🎟️"):
    action_button = _cta_button(action_url, action_label) if action_url else ""
    inner = _header(icon, title, "Master Events · masterevents.events") + _panel(f"""
        <p style="color:rgba(255,255,255,0.75);line-height:1.8;margin:0 0 24px;font-size:14px;white-space:pre-line;">{body}</p>
        {action_button}
        {_notice("purple", "SECURED BY POLYGON", "All tickets are NFTs — impossible to fake or duplicate.")}
    """) + _footer()
    return _shell(inner)


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


# ═══════════════════════════════════════════════════════════════
#  WELCOME
# ═══════════════════════════════════════════════════════════════

def notify_welcome(user):
    app_url = getattr(settings, 'FRONTEND_URL', 'https://master-events-bi7m.vercel.app')
    inner = _header("🎟️", "Welcome to Master Events", "NFT-powered ticketing", "NEW ACCOUNT", "orange") + _panel(f"""
        <p style="color:rgba(255,255,255,0.75);font-size:15px;line-height:1.7;margin:0 0 24px;">
            Hi <strong style="color:#fff;">{user.first_name}</strong> — you're now part of Master Events, where every ticket is an NFT on the Polygon blockchain. No fakes, no scalping — just real tickets, owned by you.
        </p>
        {_cta_button(app_url, "Browse Events →")}
    """) + _footer()
    _send_email_async(
        to_email=user.email,
        subject="Welcome to Master Events! 🎟️",
        html=_shell(inner),
        text=f"Hi {user.first_name},\n\nWelcome to Master Events!\nEvery ticket is an NFT on Polygon.\n\nBrowse events: {app_url}",
    )


# ═══════════════════════════════════════════════════════════════
#  PAID TICKET PURCHASE — QR lives in-app only (rotating HMAC)
# ═══════════════════════════════════════════════════════════════

def notify_ticket_purchase(ticket, static_qr_base64=None):
    user        = ticket.owner
    event       = ticket.event
    app_url     = getattr(settings, 'FRONTEND_URL', 'https://master-events-bi7m.vercel.app')
    currency    = getattr(event, 'currency', 'GHS')

    rows = [
        ("Event",    event.name,                      None),
        ("Date",     str(event.date),                 None),
        ("Venue",    event.venue,                     None),
        ("Ticket ID", ticket.ticket_id,                "#f5a623"),
        ("Quantity", f"{ticket.quantity} ticket(s)",   None),
        ("Amount",   f"{currency} {ticket.price_paid}", None),
    ]

    inner = _header("🎟️", "Booking Confirmed", event.name, "PAYMENT SUCCESSFUL", "green") + _panel(f"""
        <p style="color:rgba(255,255,255,0.75);font-size:14px;line-height:1.6;margin:0 0 24px;">
            Hi <strong style="color:#fff;">{user.first_name}</strong> — your payment was successful. Details below.
        </p>
        {_detail_card(rows)}
        {_notice("amber", "SHOW YOUR QR AT THE GATE", "Your entry QR rotates every 10 seconds for security — it lives in the app only. Do not screenshot it. Open the app at the gate for instant scanning.")}
        {_notice("purple", "NFT MINTING ON POLYGON", "Your ticket is being minted as an NFT — permanent, unforgeable, yours forever.")}
        {_cta_button(app_url, "Open App to View QR →")}
    """) + _footer()

    _send_email_async(
        to_email=user.email,
        subject=f"🎟️ Booking Confirmed — {event.name}",
        html=_shell(inner),
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
        action_url=app_url,
        action_label="View Dashboard →",
        icon="💰",
    )


# ═══════════════════════════════════════════════════════════════
#  TICKET TRANSFER
# ═══════════════════════════════════════════════════════════════

def notify_ticket_transfer(ticket, from_user, to_user, new_ticket=None, static_qr_base64=None):
    app_url = getattr(settings, 'FRONTEND_URL', 'https://master-events-bi7m.vercel.app')

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

    if new_ticket and static_qr_base64:
        qr_url = _upload_base64_qr(static_qr_base64, f"static_qr_{new_ticket.ticket_id}")

        rows = [
            ("Event", ticket.event.name, None),
            ("Date",  str(ticket.event.date), None),
            ("Venue", ticket.event.venue, None),
        ]

        inner = _header("🎟️", "You Received a Ticket!", ticket.event.name, "INCOMING TRANSFER", "orange") + _panel(f"""
            <p style="color:rgba(255,255,255,0.75);font-size:14px;line-height:1.6;margin:0 0 24px;">
                Hi <strong style="color:#fff;">{to_user.first_name}</strong> — {from_user.get_full_name() or from_user.email} just transferred a ticket to you!
            </p>
            {_detail_card(rows)}
            {_qr_card(qr_url, "Your New Backup QR")}
            <p style="color:rgba(255,255,255,0.3);font-size:11px;text-align:center;margin:-14px 0 24px;">Single-use · Invalidates on transfer</p>
            {_cta_button(app_url, "View My Ticket →")}
        """) + _footer()

        _send_email_async(
            to_email=to_user.email,
            subject=f"🎟️ You Received a Ticket — {ticket.event.name}",
            html=_shell(inner),
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


# ═══════════════════════════════════════════════════════════════
#  RESALE — all use send_notification, styled automatically
# ═══════════════════════════════════════════════════════════════

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


# ═══════════════════════════════════════════════════════════════
#  PASSWORD RESET
# ═══════════════════════════════════════════════════════════════

def notify_password_reset(user, reset_url):
    inner = _header("🔐", "Reset Your Password", "Master Events · masterevents.events") + _panel(f"""
        <p style="color:rgba(255,255,255,0.75);font-size:14px;line-height:1.8;margin:0 0 24px;">
            Hi {user.first_name} — we received a request to reset your password. Click below — this link expires in <strong style="color:#f5a623;">30 minutes</strong>.
        </p>
        {_cta_button(reset_url, "Reset Password →")}
        <p style="color:rgba(255,255,255,0.3);font-size:12px;text-align:center;margin-top:24px;">If you didn't request this, ignore this email.</p>
    """) + _footer()
    _send_email_async(
        to_email=user.email,
        subject="Master Events — Reset Your Password",
        html=_shell(inner),
        text=f"Hi {user.first_name},\n\nReset your password (expires in 30 minutes):\n{reset_url}\n\nIf you didn't request this, ignore this email.",
    )
    return True


# ═══════════════════════════════════════════════════════════════
#  FREE EVENT REGISTRATION
# ═══════════════════════════════════════════════════════════════

def notify_free_registration(reg, static_qr_base64=None):
    """Email attendee their free event registration pass"""
    user    = reg.attendee
    event   = reg.event
    app_url = getattr(settings, 'FRONTEND_URL', 'https://master-events-bi7m.vercel.app')

    qr_url = _upload_base64_qr(static_qr_base64, f"static_qr_{reg.registration_id}")

    rows = [
        ("Event",    event.name,             None),
        ("Date",     str(event.date),        None),
        ("Venue",    event.venue,            None),
        ("Spots",    str(reg.quantity),      None),
        ("Pass ID",  reg.registration_id,    "#f5a623"),
    ]

    inner = _header("🎟️", "You're In", event.name, "CONFIRMED", "green") + _panel(f"""
        <p style="color:rgba(255,255,255,0.75);font-size:14px;line-height:1.6;margin:0 0 24px;">
            Hi <strong style="color:#fff;">{user.first_name}</strong> — your spot for this event is confirmed. Details below.
        </p>
        {_detail_card(rows)}
        {_qr_card(qr_url)}
        {_notice("orange", "AT THE GATE", "Present this QR code or your Pass ID above. Open the Master Events app for a live rotating QR if this one won't scan.")}
        {_notice("purple", "SECURED BY POLYGON", "This pass can't be duplicated or faked.")}
        {_cta_button(app_url, "Open Master Events →")}
    """) + _footer()

    _send_email_async(
        to_email=user.email,
        subject=f"🎟️ You're In — {event.name}",
        html=_shell(inner),
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
    """Free event: send PDF ticket as attachment + QR in email body."""
    user    = reg.attendee
    event   = reg.event
    app_url = getattr(settings, 'FRONTEND_URL', 'https://master-events-bi7m.vercel.app')

    qr_url = _upload_base64_qr(qr_b64, f"pdf_qr_{reg.registration_id}")

    rows = [
        ("Event",   event.name,           None),
        ("Date",    str(event.date),      None),
        ("Venue",   event.venue,          None),
        ("Spots",   str(reg.quantity),    None),
        ("Pass ID", reg.registration_id,  "#f5a623"),
    ]

    pdf_notice = _notice("green", "PDF ATTACHED", "Your PDF ticket is attached — print it or save it as a backup entry pass.") if pdf_b64 else ""

    inner = _header("🎟️", "You're Registered!", f"{event.name} · Free", "CONFIRMED · NO CHARGE", "green") + _panel(f"""
        <p style="color:rgba(255,255,255,0.75);font-size:14px;line-height:1.6;margin:0 0 24px;">
            Hi <strong style="color:#fff;">{user.first_name}</strong> — your spot is confirmed, no charge.
        </p>
        {_detail_card(rows)}
        {_qr_card(qr_url, "Show this QR at the entrance")}
        {pdf_notice}
        {_notice("orange", "AT THE GATE", "Show the QR code (from this email, the attached PDF, or the app) to door staff for instant entry.")}
        {_cta_button(app_url, "Open in App →")}
    """) + _footer()

    attachments = None
    if pdf_b64:
        attachments = [{
            "filename": f"ticket-{reg.registration_id}.pdf",
            "content":  pdf_b64,
        }]

    _send_email_async(
        to_email=user.email,
        subject=f"🎟️ Your Free Ticket — {event.name}",
        html=_shell(inner),
        text=(
            f"Hi {user.first_name},\n\n"
            f"You're registered for {event.name}!\n\n"
            f"Date: {event.date}\n"
            f"Venue: {event.venue}\n"
            f"Entry Pass ID: {reg.registration_id}\n\n"
            f"Your PDF ticket is attached.\n"
            f"Open Master Events app: {app_url}"
        ),
        attachments=attachments,
    )