from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods, require_POST

from operations.forms import CustomerOwnerForm
from operations.forms.intake import IntakeWizardForm
from operations.models import ClientProfile, CustomerOwner


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