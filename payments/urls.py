from django.urls import path
from . import views

urlpatterns = [
    path('wallet/', views.wallet_detail, name='wallet'),
    path('withdraw/', views.withdraw, name='withdraw'),
    path('webhook/', views.paystack_webhook, name='paystack-webhook'),
    path('transactions/', views.transaction_history, name='transactions'),
]