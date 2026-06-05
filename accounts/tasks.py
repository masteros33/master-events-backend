def task_send_welcome_and_verification(user_id):
    """Send welcome + verification email after registration"""
    try:
        from accounts.models import User
        from utils.emails import notify_welcome
        from accounts.views import _send_verification_email

        user = User.objects.get(pk=user_id)
        try:
            notify_welcome(user)
            print(f"✅ [Q] Welcome email sent to {user.email}")
        except Exception as e:
            print(f"Welcome email failed: {e}")
        try:
            _send_verification_email(user)
            print(f"✅ [Q] Verification email sent to {user.email}")
        except Exception as e:
            print(f"Verification email failed: {e}")

    except Exception as e:
        print(f"❌ [Q] task_send_welcome_and_verification error: {e}")
        raise


def task_send_password_reset_email(user_id, reset_url):
    """Send password reset email"""
    try:
        from accounts.models import User
        from utils.emails import notify_password_reset
        user = User.objects.get(pk=user_id)
        notify_password_reset(user, reset_url)
        print(f"✅ [Q] Password reset email sent to {user.email}")
    except Exception as e:
        print(f"❌ [Q] task_send_password_reset_email error: {e}")
        raise


def task_send_resend_verification(user_id):
    """Resend verification email"""
    try:
        from accounts.models import User
        from accounts.views import _send_verification_email
        user = User.objects.get(pk=user_id)
        _send_verification_email(user)
        print(f"✅ [Q] Resend verification email sent to {user.email}")
    except Exception as e:
        print(f"❌ [Q] task_send_resend_verification error: {e}")
        raise