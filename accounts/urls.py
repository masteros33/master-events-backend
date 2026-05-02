from django.urls import path
from . import views

urlpatterns = [
    path('register/',            views.register,          name='register'),
    path('login/',               views.login,             name='login'),
    path('me/',                  views.me,                name='me'),
    path('logout/',              views.logout,            name='logout'),
    path('forgot-password/',     views.forgot_password,   name='forgot-password'),
    path('reset-password/',      views.reset_password,    name='reset-password'),
    path('notifications/',       views.notifications,     name='notifications'),
    path('notifications/read/',  views.mark_all_read,     name='mark-all-read'),
    path('sessions/',            views.active_sessions,   name='active-sessions'),
    path('sessions/revoke/',     views.revoke_all_sessions, name='revoke-sessions'),
]