from operations.models import TimelineMediaAsset, Visit, VisitTimelineEvent
from operations.services.timeline_media.errors import TimelineMediaError
from operations.services.timeline_visits import active_checked_in_visits


def validate_checked_in_visits(visit_ids: list[int]) -> list[Visit]:
    if not visit_ids:
        raise TimelineMediaError('Select at least one checked-in dog.')

    allowed_ids = set(active_checked_in_visits().values_list('pk', flat=True))
    invalid = set(visit_ids) - allowed_ids
    if invalid:
        raise TimelineMediaError('One or more selected dogs are not currently checked in.')

    visits = list(
        Visit.objects.filter(pk__in=visit_ids).select_related('client').order_by('client__dog_name'),
    )
    if len(visits) != len(set(visit_ids)):
        raise TimelineMediaError('Invalid visit selection.')
    return visits


def attach_asset_to_visits(
    *,
    asset: TimelineMediaAsset,
    visits: list[Visit],
    source_event: VisitTimelineEvent | None = None,
) -> list[VisitTimelineEvent]:
    created = []
    for visit in visits:
        if VisitTimelineEvent.objects.filter(visit=visit, media_asset=asset).exists():
            continue
        if not visit.accepts_timeline_events:
            raise TimelineMediaError(
                f'{visit.client.dog_name} is no longer checked in.',
            )
        created.append(
            VisitTimelineEvent.objects.create(
                visit=visit,
                media_asset=asset,
                source_event=source_event,
            ),
        )
    if not created:
        raise TimelineMediaError('This moment is already on the selected timelines.')
    return created
