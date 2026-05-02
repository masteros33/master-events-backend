from rest_framework.views import exception_handler
from rest_framework.response import Response
from django_ratelimit.exceptions import Ratelimited


def custom_exception_handler(exc, context):
    """Handle rate limit exceptions gracefully."""
    if isinstance(exc, Ratelimited):
        return Response(
            {'error': 'Too many requests. Please slow down and try again shortly.'},
            status=429
        )
    return exception_handler(exc, context)