from django.urls import path
from . import views

urlpatterns = [
    path('my/', views.my_tickets, name='my-tickets'),
    path('purchase/', views.purchase_ticket, name='purchase-ticket'),
    path('transfer/', views.transfer_ticket, name='transfer-ticket'),
    path('verify/', views.verify_ticket, name='verify-ticket'),
    path('door-login/', views.door_staff_login, name='door-staff-login'),
    path('event/<int:event_id>/', views.event_tickets, name='event-tickets'),
    path('event/<int:event_id>/door-code/', views.generate_door_code, name='generate-door-code'),
]