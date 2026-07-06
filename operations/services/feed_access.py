import uuid

from django.http import HttpRequest, HttpResponse

from operations.models import ClientProfile, FeedAccessLog

VISITOR_COOKIE_NAME = 'dad4dogs_feed_vid'
VISITOR_COOKIE_MAX_AGE = 60 * 60 * 24 * 365


def get_or_set_visitor_id(request: HttpRequest, response: HttpResponse | None = None) -> str:
    """Return a stable per-browser visitor ID stored in a cookie."""
    visitor_id = (request.COOKIES.get(VISITOR_COOKIE_NAME) or '').strip()
    if not visitor_id:
        visitor_id = str(uuid.uuid4())
        if response is not None:
            _set_visitor_cookie(response, visitor_id, request)
    return visitor_id


def _set_visitor_cookie(response: HttpResponse, visitor_id: str, request: HttpRequest) -> None:
    response.set_cookie(
        VISITOR_COOKIE_NAME,
        visitor_id,
        max_age=VISITOR_COOKIE_MAX_AGE,
        httponly=True,
        samesite='Lax',
        secure=request.is_secure(),
    )


def log_feed_access(
    *,
    client: ClientProfile,
    visitor_id: str,
    user_agent: str,
) -> None:
    FeedAccessLog.objects.create(
        client=client,
        visitor_id=visitor_id,
        user_agent=(user_agent or '')[:500],
    )


def feed_access_stats(client: ClientProfile, *, days: int = 30) -> dict[str, int]:
    from django.db.models import Count
    from django.utils import timezone

    since = timezone.now() - timezone.timedelta(days=days)
    stats = FeedAccessLog.objects.filter(
        client=client,
        accessed_at__gte=since,
    ).aggregate(
        views=Count('id'),
        devices=Count('visitor_id', distinct=True),
    )
    return {
        'views': stats['views'] or 0,
        'devices': stats['devices'] or 0,
    }