from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods, require_POST

from operations.forms import CustomerOwnerForm
from operations.forms.intake import (
    EvaluationScheduleForm,
    IntakeWizardForm,
    MeetGreetScheduleForm,
)
from operations.models import ClientProfile, CustomerOwner
from operations.services.visit_email import VisitEmailError, send_booking_confirmation
from operations.views.customers.clients import customer_owner_or_404


@login_required
@require_http_methods(['GET', 'POST'])
def client_intake(request):
    """Owner + first dog + optional Meet & Greet in one save."""
    if request.method == 'POST':
        form = IntakeWizardForm(request.POST)
        if form.is_valid():
            try:
                owner, dog, visit = form.save()
            except ValidationError as e:
                form.add_error(None, '; '.join(e.messages))
            else:
                if visit:
                    messages.success(
                        request,
                        f'Added {owner.owner_name} and {dog.dog_name}. '
                        f'Meet & Greet: {visit.schedule_display}.',
                    )
                else:
                    messages.success(
                        request,
                        f'Added {owner.owner_name} and {dog.dog_name}.',
                    )
                return redirect('operations:dog_detail', pk=dog.pk)
    else:
        form = IntakeWizardForm()
    return render(request, 'operations/intake_form.html', {
        'form': form,
        'title': 'New Client & Dog',
    })


@login_required
@require_http_methods(['GET', 'POST'])
def client_create(request):
    """Add customer (owner) only — no dog until one is added explicitly."""
    if request.method == 'POST':
        form = CustomerOwnerForm(request.POST)
        if form.is_valid():
            owner = form.save()
            messages.success(request, f'Added customer {owner.owner_name}. Add a dog when ready.')
            return redirect('operations:customer_detail', pk=owner.pk)
    else:
        form = CustomerOwnerForm()
    return render(request, 'operations/customer_form.html', {
        'form': form,
        'title': 'Add Customer',
        'cancel_url': 'operations:client_list',
    })


@login_required
@require_POST
def dog_create_customer(request, pk):
    """Create a CustomerOwner from a dog that has no matching customer row."""
    dog = get_object_or_404(ClientProfile, pk=pk)
    existing = CustomerOwner.for_client(dog)
    owner = CustomerOwner.ensure_for_client(dog)
    if existing is None:
        messages.success(
            request,
            f'Created customer {owner.owner_name} for {dog.dog_name}.',
        )
    else:
        messages.info(request, f'{dog.dog_name} already belongs to {owner.owner_name}.')
    return redirect('operations:customer_detail', pk=owner.pk)


@login_required
@require_http_methods(['GET', 'POST'])
def schedule_meet_greet(request, pk):
    """Dedicated one-off Meet & Greet booking (not VisitForm)."""
    dog = get_object_or_404(ClientProfile, pk=pk)
    customer_owner_or_404(dog)
    if request.method == 'POST':
        form = MeetGreetScheduleForm(request.POST, dog=dog)
        if form.is_valid():
            visit = form.save()
            messages.success(
                request,
                f'Meet & Greet booked for {dog.dog_name}: {visit.schedule_display}.',
            )
            if form.cleaned_data.get('send_confirmation_email'):
                try:
                    send_booking_confirmation(dog, [visit])
                    messages.success(request, f'Confirmation emailed to {dog.owner_email}.')
                except VisitEmailError as exc:
                    messages.warning(request, f'Booked, but email was not sent: {exc}')
            return redirect('operations:dog_detail', pk=dog.pk)
    else:
        form = MeetGreetScheduleForm(dog=dog)
    return render(request, 'operations/meet_greet_schedule.html', {
        'dog': dog,
        'form': form,
    })


@login_required
@require_http_methods(['GET', 'POST'])
def schedule_evaluation(request, pk):
    """Dedicated one-off Initial Evaluation booking (not VisitForm)."""
    dog = get_object_or_404(ClientProfile, pk=pk)
    customer_owner_or_404(dog)
    if request.method == 'POST':
        form = EvaluationScheduleForm(request.POST, dog=dog)
        if form.is_valid():
            visit = form.save()
            messages.success(
                request,
                f'Initial Evaluation booked for {dog.dog_name}: {visit.schedule_display}.',
            )
            if form.cleaned_data.get('send_confirmation_email'):
                try:
                    send_booking_confirmation(dog, [visit])
                    messages.success(request, f'Confirmation emailed to {dog.owner_email}.')
                except VisitEmailError as exc:
                    messages.warning(request, f'Booked, but email was not sent: {exc}')
            return redirect('operations:dog_detail', pk=dog.pk)
    else:
        form = EvaluationScheduleForm(dog=dog)
    return render(request, 'operations/evaluation_schedule.html', {
        'dog': dog,
        'form': form,
    })
