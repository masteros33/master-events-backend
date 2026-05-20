from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth.tokens import default_token_generator
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.core.mail import send_mail
from django.conf import settings
from django.views.decorators.cache import never_cache
from django_ratelimit.decorators import ratelimit
from django_ratelimit.exceptions import Ratelimited
from .serializers import RegisterSerializer, LoginSerializer, UserSerializer
from .models import Notification, User


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
        user = serializer.save()
        tokens = get_tokens(user)
        return Response({
            'user':   UserSerializer(user).data,
            'tokens': tokens,
        }, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([AllowAny])
@ratelimit(key='ip', rate='10/m', method='POST', block=False)
@ratelimit(key='post:email', rate='5/m', method='POST', block=False)
def login(request):
    """
    Rate limited:
    - 10 attempts per minute per IP
    - 5 attempts per minute per email (prevents targeted brute force)
    """
    if getattr(request, 'limited', False):
        return rate_limited_response()

    serializer = LoginSerializer(data=request.data)
    if serializer.is_valid():
        user = serializer.validated_data['user']
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
        # Always return success — don't leak whether email exists
        return Response({'message': 'If an account exists, a reset link has been sent.'})

    token     = default_token_generator.make_token(user)
    uid       = urlsafe_base64_encode(force_bytes(user.pk))
    reset_url = f"https://master-events-bi7m.vercel.app/reset-password?uid={uid}&token={token}"

    # ── Send email in background thread — never blocks the response ──
    import threading
    def _send():
        try:
            from utils.emails import notify_password_reset
            notify_password_reset(user, reset_url)
        except Exception as e:
            print(f"Password reset email error: {e}")

    threading.Thread(target=_send, daemon=True).start()

    # Return immediately — don't wait for email
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


# ── Session management ────────────────────────────────────────
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def active_sessions(request):
    """
    Returns info about the current session.
    In a full implementation this would list all active tokens.
    For now returns current token info + last login.
    """
    return Response({
        'email':       request.user.email,
        'last_login':  request.user.last_login,
        'is_verified': request.user.is_verified,
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
    """
    Logs out all sessions by rotating the user's password hash.
    This invalidates all existing JWT tokens.
    """
    if getattr(request, 'limited', False):
        return rate_limited_response()

    try:
        # Blacklist current refresh token if provided
        refresh_token = request.data.get('refresh')
        if refresh_token:
            token = RefreshToken(refresh_token)
            token.blacklist()
    except Exception:
        pass

    # Rotate the password hash salt — invalidates ALL existing tokens
    request.user.set_password(request.user.password)
    request.user.save(update_fields=['password'])

    return Response({'message': 'All sessions revoked. Please log in again.'})


def get_client_ip(request):
    x_forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded:
        return x_forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', 'Unknown')



@api_view(['GET'])
@permission_classes([AllowAny])
def test_email(request):
    from django.core.mail import send_mail, get_connection
    from django.conf import settings
    
    # First just return the settings so we can verify them
    config = {
        'EMAIL_HOST':      getattr(settings, 'EMAIL_HOST', 'NOT SET'),
        'EMAIL_PORT':      getattr(settings, 'EMAIL_PORT', 'NOT SET'),
        'EMAIL_HOST_USER': getattr(settings, 'EMAIL_HOST_USER', 'NOT SET'),
        'EMAIL_USE_TLS':   getattr(settings, 'EMAIL_USE_TLS', 'NOT SET'),
        'DEFAULT_FROM':    getattr(settings, 'DEFAULT_FROM_EMAIL', 'NOT SET'),
        'PASSWORD_SET':    bool(getattr(settings, 'EMAIL_HOST_PASSWORD', '')),
        'PASSWORD_LEN':    len(getattr(settings, 'EMAIL_HOST_PASSWORD', '')),
    }
    
    try:
        send_mail(
            subject='Test Email from Master Events',
            message='This is a test email.',
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=['mastereventgh@gmail.com'],
            fail_silently=False,
        )
        config['email_status'] = 'SENT successfully'
    except Exception as e:
        config['email_status'] = 'FAILED'
        config['error'] = str(e)
    
    return Response(config)