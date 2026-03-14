from django.urls import path
from . import views

urlpatterns = [
    path('', views.event_list, name='event-list'),
    path('<int:pk>/', views.event_detail, name='event-detail'),
    path('create/', views.event_create, name='event-create'),
    path('<int:pk>/update/', views.event_update, name='event-update'),
    path('<int:pk>/delete/', views.event_delete, name='event-delete'),
    path('<int:pk>/toggle-sales/', views.toggle_sales, name='toggle-sales'),
    path('my-events/', views.my_events, name='my-events'),
]