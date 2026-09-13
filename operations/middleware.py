from django.middleware.csrf import CsrfViewMiddleware
from django.utils import timezone


class NgrokCsrfMiddleware(CsrfViewMiddleware):
    """Allow ngrok HTTPS origins for CSRF checks during local development."""

    def _origin_verified(self, request):
        origin = request.META.get('HTTP_ORIGIN', '')
        if origin and (
            '.ngrok-free.app' in origin
            or '.ngrok-free.dev' in origin
            or '.ngrok.io' in origin
        ):
            return True
        return super()._origin_verified(request)


class BusinessTimezoneMiddleware:
    """Activate the business owner's Settings timezone for this request."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        from operations.services.business_timezone import get_business_timezone

        timezone.activate(get_business_timezone())
        try:
            return self.get_response(request)
        finally:
            timezone.deactivate()