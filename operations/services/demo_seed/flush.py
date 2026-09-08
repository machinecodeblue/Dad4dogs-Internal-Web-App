"""Ordered wipe of customer / visit / feed rows for the active workspace."""

from __future__ import annotations

from django.db.models import Q

from operations.models import (
    AccountStatement,
    ClientProfile,
    CustomerOwner,
    FeedAccessLog,
    MediaComment,
    MediaReaction,
    PendingCalendarEvent,
    SharedMediaLink,
    TimelineMediaAsset,
    VaccinationRecord,
    Visit,
    VisitSeries,
    VisitTimelineEvent,
)
from operations.services.context_tenant import get_active_workspace


def flush_demo_data() -> dict[str, int]:
    workspace = get_active_workspace()
    tenant_q = Q(tenant=workspace)
    counts: dict[str, int] = {}

    def _delete(label: str, qs) -> None:
        deleted, _ = qs.delete()
        counts[label] = deleted

    # Interactions → timeline links → media assets (Visit is PROTECTed by assets)
    _delete('media_comments', MediaComment.objects.filter(tenant_q))
    _delete('media_reactions', MediaReaction.objects.filter(tenant_q))
    _delete('shared_media_links', SharedMediaLink.objects.filter(tenant_q))
    _delete('visit_timeline_events', VisitTimelineEvent.objects.filter(tenant_q))
    _delete('timeline_media_assets', TimelineMediaAsset.objects.filter(tenant_q))
    _delete('feed_access_logs', FeedAccessLog.objects.filter(tenant_q))
    _delete('account_statements', AccountStatement.objects.filter(tenant_q))
    _delete('pending_calendar_events', PendingCalendarEvent.objects.filter(tenant_q))
    _delete('visits', Visit.objects.filter(tenant_q))
    _delete('visit_series', VisitSeries.objects.filter(tenant_q))
    _delete('vaccination_records', VaccinationRecord.objects.filter(tenant_q))
    _delete('client_profiles', ClientProfile.objects.filter(tenant_q))
    _delete('customer_owners', CustomerOwner.objects.filter(tenant_q))
    return counts
