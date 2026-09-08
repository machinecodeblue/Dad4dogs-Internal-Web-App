"""Visit / series / day-of scenarios on top of seeded dogs."""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.utils import timezone

from operations.models import BusinessService, Visit, VisitSeries
from operations.services import visit_calendar
from operations.services.context_tenant import get_active_workspace
from operations.services.demo_seed.owners_dogs import SeedBundle
from operations.services.pipeline import INITIAL_EVALUATION_SLUG, MEET_GREET_SLUG

TZ = ZoneInfo('America/Toronto')


def _service(slug: str) -> BusinessService:
    workspace = get_active_workspace()
    svc = BusinessService.objects.filter(tenant=workspace, slug=slug, is_active=True).first()
    if svc is None:
        raise RuntimeError(
            f'BusinessService slug="{slug}" missing. Run migrations / seed catalog first.'
        )
    return svc


def _at(day_offset: int, hour: int, minute: int = 0) -> datetime:
    local_today = timezone.localdate()
    naive = datetime(
        local_today.year, local_today.month, local_today.day,
        hour, minute,
    ) + timedelta(days=day_offset)
    return timezone.make_aware(naive, TZ)


def _create_visit(
    dog,
    *,
    start: datetime,
    end: datetime,
    service: BusinessService,
    status: str = Visit.Status.SCHEDULED,
    notes: str = '',
    skip_capacity: bool = False,
    **extra,
) -> Visit:
    visit = Visit(
        client=dog,
        business_service=service,
        scheduled_start=start,
        scheduled_end=end,
        status=status,
        notes=notes,
        **extra,
    )
    visit.save(skip_capacity=skip_capacity)
    return visit


def seed_visits(bundle: SeedBundle) -> dict[str, int]:
    overnight = _service('overnight_stay')
    daytime = _service('daytime_visit')
    meet_greet = _service(MEET_GREET_SLUG)
    evaluation = _service(INITIAL_EVALUATION_SLUG)

    ready = bundle.approved_ready()
    if len(ready) < 10:
        raise RuntimeError(f'Need ≥10 approved_ready dogs for visit scenarios, got {len(ready)}')

    counts = {
        'upcoming': 0,
        'checked_in_today': 0,
        'completed': 0,
        'cancelled': 0,
        'meet_greet': 0,
        'evaluation': 0,
        'series_visits': 0,
        'capacity_day': 0,
        'calendar_awaiting': 0,
    }

    # Upcoming boarding (next 3–10 days)
    for i, dog in enumerate(ready[:6]):
        start = _at(3 + i, 9)
        _create_visit(
            dog,
            start=start,
            end=start + timedelta(hours=8),
            service=overnight if i % 2 == 0 else daytime,
            notes='Demo upcoming boarding',
        )
        counts['upcoming'] += 1

    # Today checked-in (1–2 dogs)
    for dog in ready[6:8]:
        start = _at(0, 8)
        end = _at(0, 18)
        visit = _create_visit(
            dog,
            start=start,
            end=end,
            service=overnight,
            notes='Demo checked in today',
            skip_capacity=True,
        )
        visit.check_in()
        counts['checked_in_today'] += 1

    # Completed last week (fees)
    for i, dog in enumerate(ready[8:12]):
        start = _at(-7 + i, 9)
        end = start + timedelta(hours=8)
        visit = _create_visit(
            dog,
            start=start,
            end=end,
            service=overnight,
            notes='Demo completed stay',
            skip_capacity=True,
        )
        Visit.objects.filter(pk=visit.pk).update(
            status=Visit.Status.COMPLETED,
            actual_arrival=start,
            actual_departure=end,
            calculated_fee=Decimal('37.50'),
            fee_breakdown=[{'label': 'Overnight Stay', 'amount': '37.50'}],
        )
        counts['completed'] += 1

    # Cancelled
    dog = ready[12] if len(ready) > 12 else ready[0]
    start = _at(5, 10)
    cancelled = _create_visit(
        dog,
        start=start,
        end=start + timedelta(hours=4),
        service=daytime,
        notes='Demo cancelled',
        skip_capacity=True,
    )
    Visit.objects.filter(pk=cancelled.pk).update(status=Visit.Status.CANCELLED)
    counts['cancelled'] += 1

    # Meet & Greet: scheduled + completed Pass
    mg_dogs = bundle.dogs_by_scenario('mg_')
    if mg_dogs:
        dog = mg_dogs[0]
        start = _at(2, 14)
        _create_visit(
            dog,
            start=start,
            end=start + timedelta(minutes=15),
            service=meet_greet,
            notes='Demo M&G scheduled',
            skip_capacity=True,
        )
        counts['meet_greet'] += 1
    if len(mg_dogs) > 1:
        dog = mg_dogs[1]
        start = _at(-3, 14)
        end = start + timedelta(minutes=15)
        visit = _create_visit(
            dog,
            start=start,
            end=end,
            service=meet_greet,
            notes='Demo M&G completed pass',
            skip_capacity=True,
        )
        Visit.objects.filter(pk=visit.pk).update(
            status=Visit.Status.COMPLETED,
            actual_arrival=start,
            actual_departure=end,
            meet_greet_outcome=Visit.MeetGreetOutcome.PASS,
            meet_greet_notes='Demo: friendly meet',
            calculated_fee=Decimal('0.00'),
            fee_breakdown=[{'label': 'Meet & Greet', 'amount': '0.00'}],
        )
        counts['meet_greet'] += 1

    # Evaluation dogs: passed M&G history + one scheduled evaluation
    eval_dogs = bundle.dogs_by_scenario('eval_ready')
    for dog in eval_dogs[:2]:
        mg_start = _at(-14, 15)
        mg_end = mg_start + timedelta(minutes=15)
        mg = _create_visit(
            dog,
            start=mg_start,
            end=mg_end,
            service=meet_greet,
            notes='Demo prior M&G for evaluation dog',
            skip_capacity=True,
        )
        Visit.objects.filter(pk=mg.pk).update(
            status=Visit.Status.COMPLETED,
            actual_arrival=mg_start,
            actual_departure=mg_end,
            meet_greet_outcome=Visit.MeetGreetOutcome.PASS,
            meet_greet_notes='Passed (demo)',
            calculated_fee=Decimal('0.00'),
            fee_breakdown=[],
        )
        counts['meet_greet'] += 1

    if eval_dogs:
        dog = eval_dogs[0]
        start = _at(4, 10)
        _create_visit(
            dog,
            start=start,
            end=start + timedelta(hours=4),
            service=evaluation,
            notes='Demo evaluation scheduled',
            skip_capacity=True,
        )
        counts['evaluation'] += 1
    if len(eval_dogs) > 1:
        dog = eval_dogs[1]
        start = _at(-5, 10)
        end = start + timedelta(hours=4)
        visit = _create_visit(
            dog,
            start=start,
            end=end,
            service=evaluation,
            notes='Demo evaluation approved',
            skip_capacity=True,
        )
        Visit.objects.filter(pk=visit.pk).update(
            status=Visit.Status.COMPLETED,
            actual_arrival=start,
            actual_departure=end,
            evaluation_outcome=Visit.EvaluationOutcome.APPROVE,
            evaluation_notes='Demo: good candidate',
            calculated_fee=Decimal('15.00'),
            fee_breakdown=[{'label': 'Initial Evaluation', 'amount': '15.00'}],
        )
        counts['evaluation'] += 1

    # Repeat series (3 daily visits) on one ready dog
    series_dog = ready[0]
    series_start = _at(10, 9)
    series_end = series_start + timedelta(hours=8)
    series = VisitSeries.objects.create(
        client=series_dog,
        frequency='daily',
        interval=1,
        end_type='after',
        total_occurrences=3,
        anchor_start=series_start,
        anchor_end=series_end,
        notes='Demo repeat series',
    )
    for pos in range(3):
        start = series_start + timedelta(days=pos)
        _create_visit(
            series_dog,
            start=start,
            end=start + timedelta(hours=8),
            service=overnight,
            notes='Demo series visit',
            series=series,
            series_position=pos + 1,
            skip_capacity=True,
        )
        counts['series_visits'] += 1

    # Capacity stress day: many distinct approved dogs on same future day
    stress_day = 21
    stress_dogs = ready[:8]
    for dog in stress_dogs:
        start = _at(stress_day, 9)
        # same-dog overlap with series? ready[0] has series on day 10–12, not 21 — OK
        try:
            _create_visit(
                dog,
                start=start,
                end=start + timedelta(hours=8),
                service=overnight,
                notes='Demo capacity stress day',
            )
            counts['capacity_day'] += 1
        except Exception:
            # If blocked by ceiling, stop adding
            break

    # M&G same day as stress (capacity exempt) — should not inflate occupancy
    if mg_dogs:
        start = _at(stress_day, 11)
        _create_visit(
            mg_dogs[0],
            start=start,
            end=start + timedelta(minutes=15),
            service=meet_greet,
            notes='Demo M&G on capacity day (exempt)',
            skip_capacity=True,
        )
        counts['meet_greet'] += 1

    # Calendar awaiting confirm on 1–2 upcoming visits
    awaiting_candidates = list(
        Visit.objects.filter(
            client__in=ready[:3],
            status=Visit.Status.SCHEDULED,
            calendar_invite_state=Visit.CalendarInviteState.NONE,
        ).order_by('scheduled_start')[:2]
    )
    for visit in awaiting_candidates:
        visit_calendar.mark_awaiting_confirm(visit)
        counts['calendar_awaiting'] += 1

    return counts
