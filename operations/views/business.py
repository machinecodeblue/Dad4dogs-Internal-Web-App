from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from operations.forms import BusinessProfileForm
from operations.models import BusinessProfile


@login_required
def business_settings(request):
    profile = BusinessProfile.load()
    if request.method == 'POST':
        form = BusinessProfileForm(request.POST, instance=profile)
        if form.is_valid():
            form.save()
            messages.success(request, 'Business settings saved.')
            return redirect('operations:business_settings')
    else:
        form = BusinessProfileForm(instance=profile)

    return render(request, 'operations/business_settings.html', {
        'form': form,
        'profile': profile,
    })