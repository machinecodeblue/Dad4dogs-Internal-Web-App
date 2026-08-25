from collections import defaultdict

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_http_methods

from operations.forms import CustomerOwnerForm, DogProfileForm
from operations.models import ClientProfile, CustomerOwner
from operations.models.customers import VAX_FILTER_CHOICES
from operations.services.feed_access import feed_access_stats


def customer_owner_or_404(dog: ClientProfile) -> CustomerOwner:
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
    owners.sort(key=lambda o: o.list_sort_key)
    owner_emails = {o.owner_email.lower() for o in owners}

    customers = []
    for owner in owners:
        dogs = dogs_by_email.get(owner.owner_email.lower(), [])
        if (stage_filter or vax_filter) and not dogs:
            continue
        customers.append({'owner': owner, 'dogs': dogs})

    orphan_dogs = [
        dog for email, dogs in dogs_by_email.items()
        if email not in owner_emails
        for dog in dogs
    ]
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
@require_GET
def customer_detail(request, pk):
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
    dog = get_object_or_404(ClientProfile, pk=pk)
    customer_owner = customer_owner_or_404(dog)
    visits = dog.visits.select_related('series').all()[:20]
    return render(request, 'operations/dog_detail.html', {
        'dog': dog,
        'customer_owner': customer_owner,
        'visits': visits,
        'feed_url': dog.feed_url(request=request, create=False),
        'feed_stats': feed_access_stats(dog),
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
    customer_owner = customer_owner_or_404(dog)
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
@require_http_methods(['GET', 'POST'])
def customer_add_dog(request, pk):
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