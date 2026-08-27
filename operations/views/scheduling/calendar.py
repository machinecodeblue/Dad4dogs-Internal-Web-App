from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_POST

from operations.models import PendingCalendarEvent, Visit


@login_required
@require_GET
def pending_events(request):
    events = PendingCalendarEvent.objects.filter(
        review_status=PendingCalendarEvent.ReviewStatus.PENDING,
    ).select_related('matched_client')
    return render(request, 'operations/pending_events.html', {'events': events})


@login_required
@require_POST
def approve_pending_event(request, pk):
    event = get_object_or_404(PendingCalendarEvent, pk=pk)
    if event.matched_client:
        try:
            Visit.objects.create(
                client=event.matched_client,
                scheduled_start=event.start_datetime,
                scheduled_end=event.end_datetime,
                notes=f'From calendar: {event.summary}',
            )
        except ValidationError as e:
            messages.error(request, '; '.join(e.messages))
        else:
            event.review_status = PendingCalendarEvent.ReviewStatus.APPROVED
            event.save()
            messages.success(request, 'Calendar event approved and visit created.')
    else:
        messages.error(request, 'No matched client — assign a client in admin first.')
    return redirect('operations:pending_events')


@login_required
@require_POST
def reject_pending_event(request, pk):
    event = get_object_or_404(PendingCalendarEvent, pk=pk)
    event.review_status = PendingCalendarEvent.ReviewStatus.REJECTED
    event.save()
    messages.info(request, 'Event rejected.')
    return redirect('operations:pending_events')