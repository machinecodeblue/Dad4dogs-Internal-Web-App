from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_GET, require_POST

from operations.models import ClientProfile, CustomerOwner, Visit
from operations.services.pipeline import revert_pipeline_stage
from operations.views.customers.clients import customer_owner_or_404


@login_required
@require_POST
def dog_hide(request, pk):
    dog = get_object_or_404(ClientProfile, pk=pk)
    owner = customer_owner_or_404(dog)
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
    dog.unhide()
    messages.success(request, f'{dog.dog_name} is on the client list again.')
    return redirect('operations:dog_detail', pk=dog.pk)


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


@login_required
@require_POST
def pass_meet_greet_view(request, pk):
    """Deprecated one-click Pass — redirect staff to the M&G outcome form."""
    dog = get_object_or_404(ClientProfile, pk=pk)
    visit = (
        dog.visits.filter(
            status=Visit.Status.COMPLETED,
            business_service__slug='meet_greet',
            meet_greet_outcome='',
        )
        .order_by('-actual_departure', '-scheduled_end')
        .first()
    )
    if visit:
        messages.info(
            request,
            'Record Pass or Decline on the Meet & Greet visit (notes required).',
        )
        return redirect('operations:meet_greet_outcome', pk=visit.pk)
    messages.error(
        request,
        f'No completed Meet & Greet without an outcome for {dog.dog_name}. '
        f'Schedule and check out a Meet & Greet first.',
    )
    return redirect('operations:dog_detail', pk=pk)


@login_required
@require_POST
def revert_pipeline(request, pk):
    dog = get_object_or_404(ClientProfile, pk=pk)
    try:
        label = revert_pipeline_stage(dog)
    except ValidationError as exc:
        messages.error(request, '; '.join(exc.messages))
    else:
        messages.success(request, f'{dog.dog_name} reverted to {label}.')
    return redirect('operations:dog_detail', pk=pk)


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
def dog_feed_regenerate(request, pk):
    dog = get_object_or_404(ClientProfile, pk=pk)
    dog.regenerate_feed_secret()
    messages.success(
        request,
        f'New feed link created for {dog.dog_name}. Anyone with the old link can no longer view the feed.',
    )
    return redirect('operations:dog_detail', pk=dog.pk)


@login_required
@require_POST
def dog_delete(request, pk):
    """Legacy URL — hide, never hard-delete."""
    return dog_hide(request, pk)


@login_required
@require_GET
def client_edit(request, pk):
    """Legacy URL — redirect to dog edit."""
    return redirect('operations:dog_edit', pk=pk)


@login_required
@require_GET
def client_add_dog(request, pk):
    """Legacy URL — redirect to customer add-dog."""
    client = get_object_or_404(ClientProfile, pk=pk)
    return redirect('operations:customer_add_dog', pk=customer_owner_or_404(client).pk)


@login_required
@require_GET
def client_detail(request, pk):
    """Legacy URL — redirect to customer detail."""
    client = get_object_or_404(ClientProfile, pk=pk)
    return redirect('operations:customer_detail', pk=customer_owner_or_404(client).pk)