from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from operations.forms import BusinessProfileForm
from operations.models import BusinessProfile, CapacitySettings
from operations.services.context_tenant import get_active_workspace


@login_required
def business_settings(request):
    workspace = get_active_workspace()
    profile = BusinessProfile.load()
    capacity_settings = CapacitySettings.load()
    if request.method == 'POST':
        form = BusinessProfileForm(
            request.POST,
            instance=profile,
            capacity_settings=capacity_settings,
        )
        if form.is_valid():
            form.save()
            messages.success(request, 'Business settings saved.')
            return redirect('operations:business_settings')
    else:
        form = BusinessProfileForm(
            instance=profile,
            capacity_settings=capacity_settings,
        )

    return render(request, 'operations/business_settings.html', {
        'form': form,
        'profile': profile,
        'workspace': workspace,
        'capacity_settings': capacity_settings,
    })
