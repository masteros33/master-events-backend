from django.urls import path
from . import views

urlpatterns = [
    # Organizer wallet
    path('wallet/',                       views.wallet_detail,           name='wallet'),
    path('withdraw/',                     views.withdraw,                name='withdraw'),
    path('webhook/',                      views.paystack_webhook,        name='paystack-webhook'),
    path('transactions/',                 views.transaction_history,     name='transactions'),
    path('initialize/',                   views.initialize_payment,      name='initialize_payment'),
    # ── NEW: real recent-activity feed for the organizer dashboard —
    # replaces the frontend's previous fake Math.random()-generated
    # activity ticker with genuine recent Transaction records. ──
    path('organizer-activity/',           views.organizer_activity,      name='organizer-activity'),

    # Attendee wallet (resale earnings)
    path('attendee-wallet/',              views.attendee_wallet_detail,  name='attendee-wallet'),
    path('attendee-withdraw/',            views.attendee_withdraw,       name='attendee-withdraw'),
]