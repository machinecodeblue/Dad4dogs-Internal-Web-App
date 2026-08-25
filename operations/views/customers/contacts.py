import re

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from operations.models import ClientProfile
from operations.services.contacts import (
    analysis_to_session,
    analyze_import,
    build_vcard,
    import_selected_contacts,
    parse_google_csv,
)


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
@require_GET
def client_vcard(request, pk):
    client = get_object_or_404(ClientProfile, pk=pk)
    vcard = build_vcard(client)
    filename = re.sub(r'[^a-zA-Z0-9_-]', '_', f'{client.dog_name}_{client.owner_name}')
    filename = filename.strip('_') or 'dog'
    response = HttpResponse(vcard, content_type='text/vcard; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="{filename}.vcf"'
    return response