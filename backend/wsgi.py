import os
from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')

application = get_wsgi_application()

# Start keep-alive thread when server boots
try:
    from django.conf import settings
    if getattr(settings, 'RENDER_KEEP_ALIVE', True):
        from backend.keep_alive import start_keep_alive
        start_keep_alive()
        print("🔄 Keep-alive thread started")
except Exception as e:
    print(f"Keep-alive failed to start: {e}")