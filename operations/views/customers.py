import re
from collections import defaultdict

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from operations.forms import CustomerOwnerForm, DogProfileForm, VaccinationRecordForm
from operations.forms.intake import IntakeWizardForm
from operations.models import ClientProfile, CustomerOwner, VaccinationRecord
from operations.models.customers import VAX_FILTER_CHOICES
from operations.services.feed_access import feed_access_stats
from operations.services.contacts import (
    analysis_to_session,
    analyze_import,
    build_vcard,
    import_selected_contacts,
    parse_google_csv,
)


def _customer_owner_or_404(dog: ClientProfile) -> CustomerOwner:
    owner = CustomerOwner.for_client(dog)
    if owner is None:
        raise Http404('No customer on file for this dog.')
    return owner


@login_required
@require_GET
def client_list(request):
    stage_filter = (request.GET.get('stage') or '').strip()
    if stage_filter not in ClientProfile.PipelineStage.values:
        stage_filter = ''
    vax_filter = (request.GET.get('vax') or '').strip()
    valid_vax = {value for value, _label in VAX_FILTER_CHOICES}
    if vax_filter not in valid_vax:
        vax_filter = ''

    dogs_qs = ClientProfile.objects.visible().with_vaccination_expiry().order_by('dog_name')
    if stage_filter:
        dogs_qs = dogs_qs.filter(pipeline_stage=stage_filter)
    if vax_filter:
        dogs_qs = dogs_qs.filter_vaccination_status(vax_filter)

    dogs_by_email = defaultdict(list)
    for dog in dogs_qs:
        dogs_by_email[dog.owner_email.lower()].append(dog)

    owners = list(CustomerOwner.objects.all())
    owners.sort(key=lambda owner: owner.list_sort_key)
    owner_emails = {owner.owner_email.lower() for owner in owners}

    customers = []
    for owner in owners:
        dogs = dogs_by_email.get(owner.owner_email.lower(), [])
        if (stage_filter or vax_filter) and not dogs:
            continue
        customers.append({'owner': owner, 'dogs': dogs})

    orphan_dogs = []
    for email, dogs in dogs_by_email.items():
        if email not in owner_emails:
            orphan_dogs.extend(dogs)
    orphan_dogs.sort(key=lambda dog: dog.dog_name.lower())

    return render(request, 'operations/client_list.html', {
        'customers': customers,
        'orphan_dogs': orphan_dogs,
        'stages': ClientProfile.PipelineStage.choices,
        'current_stage': stage_filter,
        'vax_filters': VAX_FILTER_CHOICES,
        'current_vax': vax_filter,
    })


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
@require_http_methods(['GET', 'POST'])
def customer_edit(request, pk):
    owner = get_object_or_404(CustomerOwner, pk=pk)
    if request.method == 'POST':
        old_email = owner.owner_email
        form = CustomerOwnerForm(request.POST, instance=owner)
        if form.is_valid():
            with transaction.atomic():
                owner = form.save()
                ClientProfile.objects.filter(owner_email__iexact=old_email).update(
                    owner_name=owner.owner_name,
                    owner_email=owner.owner_email,
                    owner_phone=owner.owner_phone,
                )
            messages.success(request, f'Updated {owner.owner_name}.')
            return redirect('operations:customer_detail', pk=owner.pk)
    else:
        form = CustomerOwnerForm(instance=owner)
    return render(request, 'operations/customer_form.html', {
        'form': form,
        'title': f'Edit Customer — {owner.owner_name}',
        'cancel_url': 'operations:customer_detail',
        'cancel_pk': owner.pk,
    })


@login_required
@require_http_methods(['GET', 'POST'])
def dog_edit(request, pk):
    dog = get_object_or_404(ClientProfile, pk=pk)
    customer_owner = _customer_owner_or_404(dog)
    if request.method == 'POST':
        form = DogProfileForm(request.POST, instance=dog, customer_owner=customer_owner)
        if form.is_valid():
            dog = form.save()
            dog.sync_feed_dog_slug()
            messages.success(request, f'Updated {dog.dog_name}.')
            return redirect('operations:dog_detail', pk=dog.pk)
    else:
        form = DogProfileForm(instance=dog, customer_owner=customer_owner)
    return render(request, 'operations/dog_form.html', {
        'form': form,
        'title': f'Edit Dog — {dog.dog_name}',
        'customer_owner': customer_owner,
        'cancel_url': 'operations:dog_detail',
        'cancel_pk': dog.pk,
    })


@login_required
@require_POST
def dog_hide(request, pk):
    dog = get_object_or_404(ClientProfile, pk=pk)
    owner = _customer_owner_or_404(dog)
    dog.hide()
    messages.success(
        request,
        f'{dog.dog_name} is hidden from the client list. Visits and photos stay on file.',
    )
    return redirect('operations:customer_detail', pk=owner.pk)


@login_required
@require_POST
def dog_unhide(request, pk):
    dog = get_object_or_404(ClientProfile, pk=pk)
    owner = _customer_owner_or_404(dog)
    dog.unhide()
    messages.success(request, f'{dog.dog_name} is on the client list again.')
    return redirect('operations:dog_detail', pk=dog.pk)


@login_required
@require_POST
def dog_delete(request, pk):
    """Legacy URL — hide, never hard-delete (visits and photos must stay)."""
    return dog_hide(request, pk)


@login_required
@require_GET
def client_edit(request, pk):
    return redirect('operations:dog_edit', pk=pk)


@login_required
@require_GET
def client_add_dog(request, pk):
    """Legacy URL — redirect to customer add-dog."""
    client = get_object_or_404(ClientProfile, pk=pk)
    return redirect('operations:customer_add_dog', pk=_customer_owner_or_404(client).pk)


@login_required
@require_http_methods(['GET', 'POST'])
def customer_add_dog(request, pk):
    """Add a dog for an existing customer — pipeline starts at Inquiry for this dog."""
    customer_owner = get_object_or_404(CustomerOwner, pk=pk)
    if request.method == 'POST':
        form = DogProfileForm(request.POST, customer_owner=customer_owner)
        if form.is_valid():
            dog = form.save()
            messages.success(request, f'Added {dog.dog_name} for {customer_owner.owner_name}.')
            return redirect('operations:dog_detail', pk=dog.pk)
    else:
        form = DogProfileForm(
            customer_owner=customer_owner,
            initial={'pipeline_stage': ClientProfile.PipelineStage.INQUIRY},
        )
    return render(request, 'operations/dog_form.html', {
        'form': form,
        'title': f'Add Dog for {customer_owner.owner_name}',
        'customer_owner': customer_owner,
        'cancel_url': 'operations:customer_detail',
        'cancel_pk': customer_owner.pk,
    })


@login_required
@require_GET
def customer_detail(request, pk):
    """Customer (owner) front — COI and dog list only. No vaccinations."""
    customer_owner = get_object_or_404(CustomerOwner, pk=pk)
    dogs_qs = ClientProfile.objects.filter(
        owner_email__iexact=customer_owner.owner_email,
    ).with_vaccination_expiry()
    return render(request, 'operations/customer_detail.html', {
        'customer_owner': customer_owner,
        'dogs': dogs_qs.visible(),
        'hidden_dogs': dogs_qs.hidden(),
    })


@login_required
@require_GET
def dog_detail(request, pk):
    """Individual dog — visits and pipeline. No vaccinations on this screen."""
    dog = get_object_or_404(ClientProfile, pk=pk)
    customer_owner = _customer_owner_or_404(dog)
    visits = dog.visits.select_related('series').all()[:20]
    return render(request, 'operations/dog_detail.html', {
        'dog': dog,
        'customer_owner': customer_owner,
        'visits': visits,
        'feed_url': dog.feed_url(request=request, create=False),
        'feed_stats': feed_access_stats(dog),
    })


@login_required
@require_POST
def dog_feed_regenerate(request, pk):
    """Issue a new speakable feed secret — old shared links stop working."""
    dog = get_object_or_404(ClientProfile, pk=pk)
    dog.regenerate_feed_secret()
    messages.success(
        request,
        f'New feed link created for {dog.dog_name}. Anyone with the old link can no longer view the feed.',
    )
    return redirect('operations:dog_detail', pk=dog.pk)


@login_required
@require_GET
def dog_vaccinations(request, pk):
    """Vaccination records for a specific dog only."""
    dog = get_object_or_404(ClientProfile, pk=pk)
    customer_owner = _customer_owner_or_404(dog)
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
@require_GET
def client_detail(request, pk):
    """Legacy URL — open customer (owner) view."""
    client = get_object_or_404(ClientProfile, pk=pk)
    return redirect('operations:customer_detail', pk=_customer_owner_or_404(client).pk)


@login_required
@require_POST
def update_coi(request, pk):
    owner = get_object_or_404(CustomerOwner, pk=pk)
    action = request.POST.get('action')

    if action == 'mark_sent':
        owner.mark_coi_sent()
        messages.success(request, f'COI marked as sent to {owner.owner_name}.')
    elif action == 'mark_received':
        owner.mark_coi_received()
        messages.success(request, f'COI receipt confirmed for {owner.owner_name}.')
    elif action == 'reset_received':
        owner.coi_confirmed_received = False
        owner.coi_confirmed_at = None
        owner.save(update_fields=['coi_confirmed_received', 'coi_confirmed_at', 'updated_at'])
        messages.info(request, 'COI receipt confirmation cleared.')
    else:
        messages.error(request, 'Unknown action.')

    return redirect('operations:customer_detail', pk=pk)


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


@login_required
@require_GET
def client_vcard(request, pk):
    client = get_object_or_404(ClientProfile, pk=pk)
    vcard = build_vcard(client)
    filename = re.sub(r'[^a-zA-Z0-9_-]', '_', f'{client.dog_name}_{client.owner_name}')
    filename = filename.strip('_') or 'dog'
    response = HttpResponse(vcard, content_type='text/vcard; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="{filename}.vcf"'
    return response


@login_required
@require_GET
def contact_sync(request):
    last_import = request.session.get('contact_import_analysis')
    return render(request, 'operations/contact_sync.html', {
        'last_import': last_import,
    })


@login_required
@require_http_methods(['GET', 'POST'])
def contact_import_preview(request):
    if request.method == 'POST':
        uploaded = request.FILES.get('csv_file')
        if not uploaded:
            messages.error(request, 'Please choose a CSV file.')
            return redirect('operations:contact_sync')

        content = uploaded.read()
        contacts, skipped = parse_google_csv(content)
        analysis = analyze_import(contacts, skipped=skipped)
        session_data = analysis_to_session(analysis)
        request.session['contact_import_analysis'] = session_data
        return render(request, 'operations/contact_import_preview.html', {
            'analysis': session_data,
        })

    analysis = request.session.get('contact_import_analysis')
    if not analysis:
        messages.info(request, 'Upload a Google Contacts CSV to begin.')
        return redirect('operations:contact_sync')

    return render(request, 'operations/contact_import_preview.html', {
        'analysis': analysis,
    })


@login_required
@require_POST
def contact_import_selected(request):
    analysis = request.session.get('contact_import_analysis')
    if not analysis:
        messages.error(request, 'No import session found. Upload a CSV first.')
        return redirect('operations:contact_sync')

    selected_rows = []
    for raw in request.POST.getlist('selected_rows'):
        try:
            selected_rows.append(int(raw))
        except (TypeError, ValueError):
            continue
    if not selected_rows:
        messages.warning(request, 'No contacts selected.')
        return redirect('operations:contact_import_preview')

    overrides = {}
    for row_num in selected_rows:
        overrides[row_num] = {
            'dog_name': request.POST.get(f'dog_name_{row_num}', '').strip(),
            'owner_name': request.POST.get(f'owner_name_{row_num}', '').strip(),
            'owner_phone': request.POST.get(f'owner_phone_{row_num}', '').strip(),
        }

    created_owners, created_dogs, errors = import_selected_contacts(
        analysis['selectable_contacts'],
        selected_rows,
        overrides,
    )

    for error in errors:
        messages.warning(request, error)

    if created_owners:
        messages.success(request, f'Added {len(created_owners)} customer(s).')
    if created_dogs:
        names = ', '.join(d.dog_name for d in created_dogs[:5])
        suffix = f' and {len(created_dogs) - 5} more' if len(created_dogs) > 5 else ''
        messages.success(request, f'Added {len(created_dogs)} dog(s): {names}{suffix}.')

    return redirect('operations:client_list')


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
@require_POST
def advance_pipeline(request, pk):
    client = get_object_or_404(ClientProfile, pk=pk)
    if client.advance_pipeline():
        messages.success(
            request,
            f'{client.dog_name} advanced to {client.get_pipeline_stage_display()}.',
        )
    else:
        messages.info(
            request,
            f'{client.dog_name} is already {client.get_pipeline_stage_display()}.',
        )
    return redirect('operations:dog_detail', pk=pk)