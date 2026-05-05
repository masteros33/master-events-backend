import threading
import time
import requests

def start_keep_alive():
    """Ping self every 10 minutes to prevent Render free tier sleep."""
    def ping():
        while True:
            try:
                time.sleep(10 * 60)  # 10 minutes
                requests.get(
                    "https://master-events-backend.onrender.com/api/events/",
                    timeout=10
                )
                print("✅ Keep-alive ping sent")
            except Exception as e:
                print(f"Keep-alive ping failed: {e}")

    thread = threading.Thread(target=ping, daemon=True)
    thread.start()