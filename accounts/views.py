from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import authenticate
from django.contrib.auth.tokens import default_token_generator
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.conf import settings
from django_ratelimit.decorators import ratelimit
from .serializers import RegisterSerializer, LoginSerializer, UserSerializer
from .models import Notification, User
import threading


def get_tokens(user):
    refresh = RefreshToken.for_user(user)
    return {
        'refresh': str(refresh),
        'access':  str(refresh.access_token),
    }


def rate_limited_response():
    return Response(
        {'error': 'Too many attempts. Please wait before trying again.'},
        status=status.HTTP_429_TOO_MANY_REQUESTS
    )


@api_view(['POST'])
@permission_classes([AllowAny])
@ratelimit(key='ip', rate='5/m', method='POST', block=False)
def register(request):
    if getattr(request, 'limited', False):
        return rate_limited_response()

    serializer = RegisterSerializer(data=request.data)
    if serializer.is_valid():
        user   = serializer.save()
        tokens = get_tokens(user)

        # Send welcome email + verification email in background
        def _post_register():
            try:
                from utils.emails import notify_welcome
                notify_welcome(user)
            except Exception as e:
                print(f"Welcome email failed: {e}")
            try:
                _send_verification_email(user)
            except Exception as e:
                print(f"Verification email failed: {e}")

        threading.Thread(target=_post_register, daemon=True).start()

        return Response({
            'user':    UserSerializer(user).data,
            'tokens':  tokens,
            'message': 'Account created! Please check your email to verify your account.',
        }, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([AllowAny])
@ratelimit(key='ip', rate='10/m', method='POST', block=False)
@ratelimit(key='post:email', rate='5/m', method='POST', block=False)
def login(request):
    if getattr(request, 'limited', False):
        return rate_limited_response()

    serializer = LoginSerializer(data=request.data)
    if serializer.is_valid():
        user   = serializer.validated_data['user']
        tokens = get_tokens(user)
        return Response({
            'user':   UserSerializer(user).data,
            'tokens': tokens,
        })
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def me(request):
    return Response(UserSerializer(request.user).data)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def logout(request):
    try:
        refresh_token = request.data['refresh']
        token = RefreshToken(refresh_token)
        token.blacklist()
    except Exception:
        pass
    return Response({'message': 'Logged out successfully'})


@api_view(['POST'])
@permission_classes([AllowAny])
@ratelimit(key='ip', rate='3/m', method='POST', block=False)
@ratelimit(key='post:email', rate='2/m', method='POST', block=False)
def forgot_password(request):
    if getattr(request, 'limited', False):
        return rate_limited_response()

    email = request.data.get('email', '').strip().lower()
    if not email:
        return Response({'error': 'Email is required'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        user = User.objects.get(email=email)
    except User.DoesNotExist:
        return Response({'message': 'If an account exists, a reset link has been sent.'})

    token     = default_token_generator.make_token(user)
    uid       = urlsafe_base64_encode(force_bytes(user.pk))
    reset_url = f"https://master-events-bi7m.vercel.app/reset-password?uid={uid}&token={token}"

    def _send():
        try:
            from utils.emails import notify_password_reset
            notify_password_reset(user, reset_url)
        except Exception as e:
            print(f"Password reset email error: {e}")
    threading.Thread(target=_send, daemon=True).start()

    return Response({'message': 'Password reset link sent to your email.'})


@api_view(['POST'])
@permission_classes([AllowAny])
@ratelimit(key='ip', rate='5/m', method='POST', block=False)
def reset_password(request):
    if getattr(request, 'limited', False):
        return rate_limited_response()

    uid          = request.data.get('uid', '')
    token        = request.data.get('token', '')
    new_password = request.data.get('new_password', '')

    if not uid or not token or not new_password:
        return Response({'error': 'Missing required fields'}, status=status.HTTP_400_BAD_REQUEST)

    if len(new_password) < 8:
        return Response(
            {'error': 'Password must be at least 8 characters'},
            status=status.HTTP_400_BAD_REQUEST
        )

    try:
        user_id = force_str(urlsafe_base64_decode(uid))
        user    = User.objects.get(pk=user_id)
    except (TypeError, ValueError, User.DoesNotExist):
        return Response({'error': 'Invalid reset link'}, status=status.HTTP_400_BAD_REQUEST)

    if not default_token_generator.check_token(user, token):
        return Response(
            {'error': 'Reset link expired or invalid'},
            status=status.HTTP_400_BAD_REQUEST
        )

    user.set_password(new_password)
    user.save()
    return Response({'message': 'Password reset successfully. You can now log in.'})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def notifications(request):
    notifs = Notification.objects.filter(user=request.user)[:20]
    data = [{
        'id':         n.id,
        'type':       n.type,
        'title':      n.title,
        'body':       n.body,
        'is_read':    n.is_read,
        'created_at': n.created_at.isoformat(),
    } for n in notifs]
    return Response(data)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def mark_all_read(request):
    Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
    return Response({'message': 'All marked as read'})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def active_sessions(request):
    return Response({
        'email':       request.user.email,
        'last_login':  request.user.last_login,
        'is_verified': getattr(request.user, 'is_verified', False),
        'role':        request.user.role,
        'sessions': [{
            'id':         'current',
            'device':     request.META.get('HTTP_USER_AGENT', 'Unknown device')[:80],
            'ip':         get_client_ip(request),
            'created_at': request.user.last_login,
            'is_current': True,
        }]
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@ratelimit(key='user', rate='3/m', method='POST', block=False)
def revoke_all_sessions(request):
    if getattr(request, 'limited', False):
        return rate_limited_response()
    try:
        refresh_token = request.data.get('refresh')
        if refresh_token:
            token = RefreshToken(refresh_token)
            token.blacklist()
    except Exception:
        pass
    request.user.set_password(request.user.password)
    request.user.save(update_fields=['password'])
    return Response({'message': 'All sessions revoked. Please log in again.'})


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def delete_account(request):
    """Requires password confirmation before deleting"""
    password = request.data.get('password', '')
    if not password:
        return Response({'error': 'Password is required to delete account'}, status=400)
    if not request.user.check_password(password):
        return Response({'error': 'Incorrect password'}, status=400)
    email = request.user.email
    request.user.delete()
    print(f"✅ Account deleted: {email}")
    return Response({'message': 'Account deleted successfully'})


def get_client_ip(request):
    x_forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded:
        return x_forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', 'Unknown')


@api_view(['GET'])
@permission_classes([AllowAny])
def test_email(request):
    import resend
    config = {
        'RESEND_API_KEY_SET': bool(getattr(settings, 'RESEND_API_KEY', '')),
        'RESEND_KEY_LEN':     len(getattr(settings, 'RESEND_API_KEY', '')),
        'DEFAULT_FROM':       getattr(settings, 'DEFAULT_FROM_EMAIL', 'NOT SET'),
    }

    def _send():
        try:
            resend.api_key = settings.RESEND_API_KEY
            r = resend.Emails.send({
                "from":    settings.DEFAULT_FROM_EMAIL,
                "to":      ["mastereventgh@gmail.com"],
                "subject": "✅ Master Events — Email Test",
                "html":    "<h1 style='color:#f5a623'>Master Events email is working! 🎟️</h1>",
                "text":    "Master Events email is working!",
            })
            print(f"✅ Resend test email sent: {r}")
        except Exception as e:
            print(f"❌ Resend error: {e}")

    threading.Thread(target=_send, daemon=True).start()
    config['status'] = 'dispatched — check Render logs + your inbox in 10 seconds'
    return Response(config)


# ── Admin login — FIXED (was indented inside test_email) ──────
@api_view(['POST'])
@permission_classes([AllowAny])
def admin_login(request):
    email    = request.data.get('email', '').strip()
    password = request.data.get('password', '')
    if not email or not password:
        return Response({'error': 'Email and password required'}, status=400)

    user = authenticate(request, email=email, password=password)
    if user and user.role == 'super_admin':
        tokens = get_tokens(user)
        return Response({
            'tokens': tokens,
            'user': {
                'id':         user.id,
                'email':      user.email,
                'first_name': user.first_name,
                'last_name':  user.last_name,
                'role':       user.role,
            }
        })
    return Response(
        {'error': 'Invalid credentials or insufficient permissions'},
        status=401
    )


# ── Super Admin: platform overview ───────────────────────────
def is_super_admin(user):
    return user.is_authenticated and user.role == 'super_admin'


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def admin_overview(request):
    if not is_super_admin(request.user):
        return Response({'error': 'Forbidden'}, status=403)

    from events.models import Event
    from tickets.models import Ticket
    from payments.models import Wallet, Transaction

    total_users      = User.objects.count()
    total_attendees  = User.objects.filter(role='attendee').count()
    total_organizers = User.objects.filter(role='organizer').count()
    total_events     = Event.objects.count()
    active_events    = Event.objects.filter(sales_open=True, is_active=True).count()
    total_tickets    = Ticket.objects.count()
    total_revenue    = sum(
        float(w.total_earned)
        for w in Wallet.objects.all()
    )
    total_withdrawn  = sum(
        float(w.total_withdrawn)
        for w in Wallet.objects.all()
    )

    return Response({
        'users': {
            'total':      total_users,
            'attendees':  total_attendees,
            'organizers': total_organizers,
        },
        'events': {
            'total':  total_events,
            'active': active_events,
        },
        'tickets': {
            'total': total_tickets,
        },
        'revenue': {
            'total_earned':    round(total_revenue, 2),
            'total_withdrawn': round(total_withdrawn, 2),
            'platform_fees':   round(total_revenue * 0.05, 2),
        },
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def admin_organizers(request):
    if not is_super_admin(request.user):
        return Response({'error': 'Forbidden'}, status=403)

    from events.models import Event
    from payments.models import Wallet

    organizers = User.objects.filter(role='organizer').order_by('-date_joined')
    data = []
    for org in organizers:
        events  = Event.objects.filter(organizer=org)
        wallet  = Wallet.objects.filter(user=org).first()
        data.append({
            'id':           org.id,
            'name':         org.full_name,
            'email':        org.email,
            'phone':        org.phone,
            'is_verified':  org.is_verified,
            'is_suspended': getattr(org, 'is_suspended', False),
            'joined':       org.date_joined.isoformat(),
            'events_count': events.count(),
            'tickets_sold': sum(e.tickets_sold for e in events),
            'total_earned': float(wallet.total_earned) if wallet else 0,
            'balance':      float(wallet.balance) if wallet else 0,
        })
    return Response(data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def admin_events(request):
    if not is_super_admin(request.user):
        return Response({'error': 'Forbidden'}, status=403)

    from events.models import Event
    events = Event.objects.select_related('organizer').order_by('-created_at')[:100]
    data = [{
        'id':            e.id,
        'name':          e.name,
        'organizer':     e.organizer.full_name,
        'organizer_email': e.organizer.email,
        'date':          str(e.date),
        'venue':         e.venue,
        'category':      e.category,
        'price':         float(e.price),
        'total_tickets': e.total_tickets,
        'tickets_sold':  e.tickets_sold,
        'sales_open':    e.sales_open,
        'is_active':     e.is_active,
        'revenue':       round(float(e.price) * e.tickets_sold * 0.95, 2),
    } for e in events]
    return Response(data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def admin_transactions(request):
    if not is_super_admin(request.user):
        return Response({'error': 'Forbidden'}, status=403)

    from payments.models import Transaction
    txns = Transaction.objects.select_related('wallet__user').order_by('-created_at')[:200]
    data = [{
        'id':          t.id,
        'type':        t.type,
        'amount':      float(t.amount),
        'description': t.description,
        'reference':   t.reference,
        'status':      t.status,
        'user':        t.wallet.user.email if t.wallet else 'N/A',
        'created_at':  t.created_at.isoformat(),
    } for t in txns]
    return Response(data)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def admin_suspend_user(request, user_id):
    if not is_super_admin(request.user):
        return Response({'error': 'Forbidden'}, status=403)
    try:
        user = User.objects.get(pk=user_id)
    except User.DoesNotExist:
        return Response({'error': 'User not found'}, status=404)
    user.is_suspended = not getattr(user, 'is_suspended', False)
    user.save(update_fields=['is_suspended'])
    action = 'suspended' if user.is_suspended else 'reinstated'
    return Response({'message': f'User {action}', 'is_suspended': user.is_suspended})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def admin_toggle_event(request, event_id):
    if not is_super_admin(request.user):
        return Response({'error': 'Forbidden'}, status=403)
    from events.models import Event
    try:
        event = Event.objects.get(pk=event_id)
    except Event.DoesNotExist:
        return Response({'error': 'Event not found'}, status=404)
    event.is_active = not event.is_active
    event.save(update_fields=['is_active'])
    return Response({'message': f'Event {"activated" if event.is_active else "deactivated"}', 'is_active': event.is_active})




    # ── Email verification helpers ────────────────────────────────
def _send_verification_email(user):
    from .models import EmailVerificationToken
    # Delete any existing token
    EmailVerificationToken.objects.filter(user=user).delete()
    # Create new token
    vt        = EmailVerificationToken.objects.create(user=user)
    token_str = str(vt.token)
    verify_url = f"{settings.FRONTEND_URL}?verify={token_str}"

    import resend
    resend.api_key = settings.RESEND_API_KEY
    html = f"""
    <!DOCTYPE html>
    <html>
    <head><meta charset="UTF-8"></head>
    <body style="margin:0;padding:0;background:#0f0f0f;font-family:'Helvetica Neue',Arial,sans-serif;">
        <div style="max-width:600px;margin:0 auto;padding:24px 16px;">
            <div style="background:linear-gradient(135deg,#F97316,#EA6C0A);border-radius:20px 20px 0 0;padding:32px;text-align:center;">
                <div style="font-size:32px;margin-bottom:8px;">✉️</div>
                <h1 style="margin:0;color:#fff;font-size:22px;font-weight:900;">Verify Your Email</h1>
                <p style="margin:6px 0 0;color:rgba(255,255,255,0.8);font-size:13px;">Master Events Ghana</p>
            </div>
            <div style="background:#1a1a1a;padding:32px;border-left:1px solid #2a2a2a;border-right:1px solid #2a2a2a;">
                <p style="color:rgba(255,255,255,0.75);font-size:15px;line-height:1.8;margin:0 0 24px;">
                    Hi {user.first_name},<br><br>
                    Thanks for joining Master Events! Click below to verify your email address.
                    This link expires in <strong style="color:#F97316;">24 hours</strong>.
                </p>
                <div style="text-align:center;margin:28px 0;">
                    <a href="{verify_url}"
                       style="background:linear-gradient(135deg,#F97316,#EA6C0A);color:#fff;padding:16px 40px;border-radius:12px;text-decoration:none;font-weight:700;font-size:16px;display:inline-block;">
                        Verify Email →
                    </a>
                </div>
                <p style="color:rgba(255,255,255,0.35);font-size:12px;text-align:center;">
                    If you didn't create an account, ignore this email.
                </p>
            </div>
            <div style="background:#111;border-radius:0 0 20px 20px;border:1px solid #2a2a2a;border-top:none;padding:16px;text-align:center;">
                <p style="color:rgba(255,255,255,0.2);font-size:10px;margin:0;">© 2026 Master Events Ghana</p>
            </div>
        </div>
    </body>
    </html>
    """
    resend.Emails.send({
        "from":    settings.DEFAULT_FROM_EMAIL,
        "to":      [user.email],
        "subject": "Master Events — Verify Your Email",
        "html":    html,
        "text":    f"Hi {user.first_name},\n\nVerify your email:\n{verify_url}\n\nExpires in 24 hours.",
    })
    print(f"✅ Verification email sent to {user.email}")


@api_view(['POST'])
@permission_classes([AllowAny])
def verify_email(request):
    """Verify email with token from URL"""
    token_str = request.data.get('token', '').strip()
    if not token_str:
        return Response({'error': 'Token is required'}, status=400)

    from .models import EmailVerificationToken
    from django.utils import timezone
    from datetime import timedelta

    try:
        import uuid
        token_uuid = uuid.UUID(token_str)
        vt = EmailVerificationToken.objects.select_related('user').get(token=token_uuid)
    except (ValueError, EmailVerificationToken.DoesNotExist):
        return Response({'error': 'Invalid verification token'}, status=400)

    # Check expiry — 24 hours
    if timezone.now() > vt.created_at + timedelta(hours=24):
        vt.delete()
        return Response({'error': 'Verification link expired. Please request a new one.'}, status=400)

    # Mark verified
    user = vt.user
    user.is_verified = True
    user.save(update_fields=['is_verified'])
    vt.delete()

    return Response({
        'message': 'Email verified successfully! You can now use all features.',
        'email':   user.email,
    })


@api_view(['POST'])
@permission_classes([AllowAny])
@ratelimit(key='ip', rate='3/m', method='POST', block=False)
def resend_verification(request):
    """Resend verification email"""
    if getattr(request, 'limited', False):
        return rate_limited_response()

    email = request.data.get('email', '').strip().lower()
    if not email:
        return Response({'error': 'Email is required'}, status=400)

    try:
        user = User.objects.get(email=email)
    except User.DoesNotExist:
        # Don't reveal if email exists
        return Response({'message': 'If an account exists, a verification email has been sent.'})

    if user.is_verified:
        return Response({'message': 'This email is already verified.'})

    threading.Thread(
        target=_send_verification_email,
        args=(user,),
        daemon=True
    ).start()

    return Response({'message': 'Verification email sent. Check your inbox.'})