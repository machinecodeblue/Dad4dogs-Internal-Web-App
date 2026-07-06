from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from operations.forms import CustomerOwnerForm, DogProfileForm, VaccinationRecordForm
from operations.models import ClientProfile, CustomerOwner, VaccinationRecord
from operations.services.feed_access import feed_access_stats
from operations.services.contacts import (
    analysis_to_session,
    analyze_import,
    build_vcard,
    import_selected_contacts,
    parse_google_csv,
)


@login_required
def client_list(request):
    stage_filter = request.GET.get('stage')
    customers = []
    for owner in CustomerOwner.objects.all().order_by('owner_name'):
        dogs = ClientProfile.objects.filter(owner_email__iexact=owner.owner_email)
        if stage_filter:
            dogs = dogs.filter(pipeline_stage=stage_filter)
            if not dogs.exists():
                continue
        customers.append({'owner': owner, 'dogs': dogs})

    return render(request, 'operations/client_list.html', {
        'customers': customers,
        'stages': ClientProfile.PipelineStage.choices,
        'current_stage': stage_filter,
    })


@login_required
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
def customer_edit(request, pk):
    owner = get_object_or_404(CustomerOwner, pk=pk)
    if request.method == 'POST':
        form = CustomerOwnerForm(request.POST, instance=owner)
        if form.is_valid():
            old_email = owner.owner_email
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
def dog_edit(request, pk):
    dog = get_object_or_404(ClientProfile, pk=pk)
    customer_owner = CustomerOwner.ensure_for_client(dog)
    if request.method == 'POST':
        form = DogProfileForm(request.POST, instance=dog, customer_owner=customer_owner)
        if form.is_valid():
            dog = form.save()
            dog.ensure_feed_credentials()
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
def dog_delete(request, pk):
    dog = get_object_or_404(ClientProfile, pk=pk)
    owner_pk = dog.customer_owner.pk
    name = dog.dog_name
    dog.delete()
    messages.success(request, f'Removed dog {name}.')
    return redirect('operations:customer_detail', pk=owner_pk)


@login_required
def client_edit(request, pk):
    return redirect('operations:dog_edit', pk=pk)


@login_required
def client_add_dog(request, pk):
    """Legacy URL — redirect to customer add-dog."""
    client = get_object_or_404(ClientProfile, pk=pk)
    return redirect('operations:customer_add_dog', pk=client.customer_owner.pk)


@login_required
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
def customer_detail(request, pk):
    """Customer (owner) front — COI and dog list only. No vaccinations."""
    customer_owner = get_object_or_404(CustomerOwner, pk=pk)
    dogs = ClientProfile.objects.filter(owner_email__iexact=customer_owner.owner_email)
    return render(request, 'operations/customer_detail.html', {
        'customer_owner': customer_owner,
        'dogs': dogs,
    })


@login_required
def dog_detail(request, pk):
    """Individual dog — visits and pipeline. No vaccinations on this screen."""
    dog = get_object_or_404(ClientProfile, pk=pk)
    customer_owner = CustomerOwner.ensure_for_client(dog)
    dog.ensure_feed_credentials()
    visits = dog.visits.select_related('series').all()[:20]
    return render(request, 'operations/dog_detail.html', {
        'dog': dog,
        'customer_owner': customer_owner,
        'visits': visits,
        'feed_url': dog.feed_url(request=request),
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
def dog_vaccinations(request, pk):
    """Vaccination records for a specific dog only."""
    dog = get_object_or_404(ClientProfile, pk=pk)
    customer_owner = CustomerOwner.ensure_for_client(dog)
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
def client_detail(request, pk):
    """Legacy URL — open customer (owner) view."""
    client = get_object_or_404(ClientProfile, pk=pk)
    return redirect('operations:customer_detail', pk=client.customer_owner.pk)


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
    else:
        for field, errors in form.errors.items():
            for error in errors:
                messages.error(request, f'{field}: {error}')
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
def client_vcard(request, pk):
    client = get_object_or_404(ClientProfile, pk=pk)
    vcard = build_vcard(client)
    filename = f'{client.dog_name}_{client.owner_name}'.replace(' ', '_')
    response = HttpResponse(vcard, content_type='text/vcard; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="{filename}.vcf"'
    return response


@login_required
def contact_sync(request):
    last_import = request.session.get('contact_import_analysis')
    return render(request, 'operations/contact_sync.html', {
        'last_import': last_import,
    })


@login_required
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

    selected_rows = [int(r) for r in request.POST.getlist('selected_rows')]
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
def advance_pipeline(request, pk):
    client = get_object_or_404(ClientProfile, pk=pk)
    client.advance_pipeline()
    messages.success(request, f'{client.dog_name} advanced to {client.get_pipeline_stage_display()}.')
    return redirect('operations:dog_detail', pk=pk)