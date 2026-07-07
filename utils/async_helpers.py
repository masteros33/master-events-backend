import threading

def run_async(func, *args, **kwargs):
    """
    Run a function in a background thread — fire and forget.
    Replaces django_q's async_task() since no qcluster worker
    is running on Render's free tier.
    """
    thread = threading.Thread(target=func, args=args, kwargs=kwargs, daemon=True)
    thread.start()
    return thread