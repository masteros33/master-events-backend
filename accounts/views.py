from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
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

        # Send welcome email in background
        def _welcome():
            try:
                from utils.emails import notify_welcome
                notify_welcome(user)
            except Exception as e:
                print(f"Welcome email failed: {e}")
        threading.Thread(target=_welcome, daemon=True).start()

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