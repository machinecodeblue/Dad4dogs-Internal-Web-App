from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from operations.forms import VaccinationRecordForm
from operations.models import ClientProfile, VaccinationRecord
from operations.views.customers.clients import customer_owner_or_404


@login_required
@require_GET
def dog_vaccinations(request, pk):
    dog = get_object_or_404(ClientProfile, pk=pk)
    customer_owner = customer_owner_or_404(dog)
    vaccinations = dog.vaccination_records.all()
    has_expired_validated = (
        not dog.has_current_vaccination
        and vaccinations.filter(validated=True).exists()
    )
    return render(request, 'operations/dog_vaccinations.html', {
        'dog': dog,
        'customer_owner': customer_owner,
        'vaccinations': vaccinations,
        'vaccination_form': VaccinationRecordForm(fixed_client=dog),
        'has_expired_validated': has_expired_validated,
    })


@login_required
@require_POST
def add_vaccination(request, pk):
    client = get_object_or_404(ClientProfile, pk=pk)
    form = VaccinationRecordForm(request.POST, fixed_client=client)
    if form.is_valid():
        record = form.save()
        messages.success(
            request,
            f'Vaccination record added for {record.client.dog_name}.',
        )
        if record.expires_at < timezone.localdate():
            messages.warning(
                request,
                f'That expiry is already in the past. {record.client.dog_name} '
                f'is not current until new papers are on file.',
            )
    else:
        for error in form.non_field_errors():
            messages.error(request, error)
        for name, field in form.fields.items():
            if name not in form.errors:
                continue
            label = field.label or name.replace('_', ' ')
            for error in form.errors[name]:
                messages.error(request, f'{label}: {error}')
    return redirect('operations:dog_vaccinations', pk=pk)


@login_required
@require_POST
def validate_vaccination(request, pk, record_pk):
    dog = get_object_or_404(ClientProfile, pk=pk)
    record = get_object_or_404(VaccinationRecord, pk=record_pk, client=dog)
    record.mark_validated()
    messages.success(
        request,
        f'Vaccination papers validated for {dog.dog_name}.',
    )
    return redirect('operations:dog_vaccinations', pk=pk)