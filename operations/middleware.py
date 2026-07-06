from django.middleware.csrf import CsrfViewMiddleware


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