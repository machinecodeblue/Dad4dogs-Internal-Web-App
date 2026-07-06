from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.views.decorators.http import require_GET


@require_GET
def manifest(request):
    """Web App Manifest for install-to-home-screen (standalone display)."""
    icon_base = f'{settings.STATIC_URL}operations/pwa'
    payload = {
        'name': 'Dad4dogs',
        'short_name': 'Dad4dogs',
        'description': "David's Internal Operations",
        'start_url': '/',
        'scope': '/',
        'display': 'standalone',
        'orientation': 'portrait-primary',
        'background_color': '#2d6a4f',
        'theme_color': '#2d6a4f',
        'icons': [
            {
                'src': f'{icon_base}/icon-192.png',
                'sizes': '192x192',
                'type': 'image/png',
                'purpose': 'any',
            },
            {
                'src': f'{icon_base}/icon-512.png',
                'sizes': '512x512',
                'type': 'image/png',
                'purpose': 'any',
            },
            {
                'src': f'{icon_base}/icon-maskable-512.png',
                'sizes': '512x512',
                'type': 'image/png',
                'purpose': 'maskable',
            },
        ],
    }
    response = JsonResponse(payload)
    response['Content-Type'] = 'application/manifest+json'
    response['Cache-Control'] = 'public, max-age=3600'
    return response


@require_GET
def service_worker(request):
    """
    Minimal service worker — enables PWA install without caching authenticated pages.
    """
    body = """const SW_VERSION = 'dad4dogs-v1';

self.addEventListener('install', (event) => {
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(self.clients.claim());
});

self.addEventListener('fetch', (event) => {
  event.respondWith(fetch(event.request));
});
"""
    response = HttpResponse(body, content_type='application/javascript')
    response['Service-Worker-Allowed'] = '/'
    response['Cache-Control'] = 'no-cache'
    return response