from django.urls import path
from . import views

urlpatterns = [
    # Organizer wallet
    path('wallet/',                       views.wallet_detail,           name='wallet'),
    path('withdraw/',                     views.withdraw,                name='withdraw'),
    path('webhook/',                      views.paystack_webhook,        name='paystack-webhook'),
    path('transactions/',                 views.transaction_history,     name='transactions'),
    path('initialize/',                   views.initialize_payment,      name='initialize_payment'),

    # Attendee wallet (resale earnings)
    path('attendee-wallet/',              views.attendee_wallet_detail,  name='attendee-wallet'),
    path('attendee-withdraw/',            views.attendee_withdraw,       name='attendee-withdraw'),
]