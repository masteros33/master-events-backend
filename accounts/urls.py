from django.urls import path
from . import views

urlpatterns = [
    path('register/',             views.register,            name='register'),
    path('login/',                views.login,               name='login'),
    path('me/',                   views.me,                  name='me'),
    path('me/update/',            views.update_profile,      name='update-profile'),
    path('me/change-password/',   views.change_password,     name='change-password'),
    path('me/wallet/',            views.update_wallet,       name='update-wallet'),
    path('logout/',               views.logout,              name='logout'),
    path('forgot-password/',      views.forgot_password,     name='forgot-password'),
    path('reset-password/',       views.reset_password,      name='reset-password'),
    path('verify-email/',         views.verify_email,        name='verify-email'),
    path('resend-verification/',  views.resend_verification, name='resend-verification'),
    path('notifications/',        views.notifications,       name='notifications'),
    path('notifications/read/',   views.mark_all_read,       name='mark-all-read'),
    path('sessions/',             views.active_sessions,     name='active-sessions'),
    path('sessions/revoke/',      views.revoke_all_sessions, name='revoke-sessions'),
    path('test-email/',           views.test_email,          name='test-email'),
    path('delete-account/',       views.delete_account,      name='delete-account'),

    # ── Super Admin ───────────────────────────────────────────
    path('admin/login/',                          views.admin_login,         name='admin-login'),
    path('admin/overview/',                       views.admin_overview,      name='admin-overview'),
    path('admin/organizers/',                     views.admin_organizers,    name='admin-organizers'),
    path('admin/events/',                         views.admin_events,        name='admin-events'),
    path('admin/transactions/',                   views.admin_transactions,  name='admin-transactions'),
    path('admin/users/<int:user_id>/suspend/',    views.admin_suspend_user,  name='admin-suspend-user'),
    path('admin/events/<int:event_id>/toggle/',   views.admin_toggle_event,  name='admin-toggle-event'),
    path('google/',  views.google_auth,  name='google-auth'),
]