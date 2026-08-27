from datetime import datetime

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods, require_POST

from operations.forms import VisitForm
from operations.models import ClientProfile, Visit
from operations.services.datetime_parse import parse_datetime_text
from operations.services.visit_email import VisitEmailError, send_booking_confirmation
from operations.services.visit_repeat import FREQUENCY_NONE, repeat_summary
from operations.views.scheduling.helpers import apply_visit_form_errors


@login_required
@require_http_methods(['GET', 'POST'])
def visit_create(request, pk):
    client = get_object_or_404(ClientProfile, pk=pk)
    client_visits = client.visits.filter(status=Visit.Status.COMPLETED)[:10]
    visit_form = VisitForm(client=client)

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'create':
            visit_form = VisitForm(request.POST, client=client)
            if visit_form.is_valid():
                try:
                    visits = visit_form.save_all()
                    if len(visits) > 1:
                        pairs = [(v.scheduled_start, v.scheduled_end) for v in visits]
                        freq = visit_form.cleaned_data.get('repeat_frequency', FREQUENCY_NONE)
                        interval = visit_form.cleaned_data.get('repeat_interval') or 1
                        summary = repeat_summary(pairs, freq, interval)
                        messages.success(request, f'Scheduled {client.dog_name}: {summary}')
                    else:
                        messages.success(request, f'Scheduled {client.dog_name}: {visits[0].schedule_display}')
                    if visit_form.cleaned_data.get('send_confirmation_email'):
                        try:
                            send_booking_confirmation(client, visits)
                            messages.success(request, f'Confirmation email sent to {client.owner_email}.')
                        except VisitEmailError as exc:
                            messages.warning(request, f'Visit booked, but confirmation email was not sent: {exc}')
                    return redirect('operations:dog_detail', pk=client.pk)
                except ValidationError as e:
                    apply_visit_form_errors(visit_form, e)
        elif action == 'clone':
            new_date_str = request.POST.get('new_date', '').strip()
            new_date_text = request.POST.get('new_date_text', '').strip()
            visit_id = request.POST.get('visit_id')
            if not visit_id:
                messages.error(request, 'Select a past visit to clone.')
            else:
                source = get_object_or_404(Visit, pk=visit_id, client=client)
                try:
                    if new_date_str:
                        new_date = datetime.strptime(new_date_str, '%Y-%m-%d').date()
                    elif new_date_text:
                        new_date = parse_datetime_text(new_date_text).date()
                    else:
                        raise ValidationError('Enter the new start date.')
                    cloned = source.clone_to_date(new_date)
                    messages.success(request, f'Cloned visit for {client.dog_name}: {cloned.schedule_display}')
                    return redirect('operations:dog_detail', pk=client.pk)
                except ValidationError as e:
                    messages.error(request, '; '.join(e.messages))

    return render(request, 'operations/visit_form.html', {
        'client': client,
        'visits': client_visits,
        'visit_form': visit_form,
        'visit': None,
        'title': f'Schedule Visit — {client.dog_name}',
        'submit_label': 'Schedule Visit',
        'show_clone': True,
    })


@login_required
@require_http_methods(['GET', 'POST'])
def duplicate_visit(request, pk):
    """Legacy URL — same as visit_create."""
    return visit_create(request, pk)


@login_required
@require_http_methods(['GET', 'POST'])
def visit_edit(request, pk):
    visit = get_object_or_404(Visit, pk=pk)
    if not visit.is_editable:
        messages.error(request, 'Only scheduled visits can be edited.')
        return redirect('operations:dog_detail', pk=visit.client_id)

    visit_form = VisitForm(instance=visit)
    if request.method == 'POST':
        visit_form = VisitForm(request.POST, instance=visit)
        if visit_form.is_valid():
            try:
                visit = visit_form.save()
                messages.success(request, f'Updated visit for {visit.client.dog_name}: {visit.schedule_display}')
                return redirect('operations:dog_detail', pk=visit.client_id)
            except ValidationError as e:
                apply_visit_form_errors(visit_form, e)

    return render(request, 'operations/visit_form.html', {
        'client': visit.client,
        'visit_form': visit_form,
        'title': f'Edit Visit — {visit.client.dog_name}',
        'submit_label': 'Save Visit',
        'show_clone': False,
        'visit': visit,
    })


@login_required
@require_POST
def visit_send_confirmation(request, pk):
    """Email a booking confirmation for one visit that has not been sent yet."""
    visit = get_object_or_404(Visit.objects.select_related('client'), pk=pk)
    dog_pk = visit.client_id
    if visit.status == Visit.Status.CANCELLED:
        messages.error(request, 'Cancelled visits cannot be emailed.')
        return redirect('operations:dog_detail', pk=dog_pk)
    if visit.confirmation_email_sent_at:
        messages.info(request, 'Confirmation email was already sent for this visit.')
        return redirect('operations:dog_detail', pk=dog_pk)
    try:
        send_booking_confirmation(visit.client, [visit])
        messages.success(request, f'Confirmation email sent to {visit.client.owner_email}.')
    except VisitEmailError as exc:
        messages.warning(request, f'Confirmation email was not sent: {exc}')
    return redirect('operations:dog_detail', pk=dog_pk)


@login_required
@require_POST
def visit_delete(request, pk):
    visit = get_object_or_404(Visit, pk=pk)
    dog_pk = visit.client_id
    dog_name = visit.client.dog_name
    if not visit.is_editable:
        messages.error(request, 'Only scheduled visits can be removed.')
        return redirect('operations:dog_detail', pk=dog_pk)
    visit.delete()
    messages.success(request, f'Removed scheduled visit for {dog_name}.')
    return redirect('operations:dog_detail', pk=dog_pk)