from operations.models import ClientProfile, CustomerOwner
from operations.services.phones import validate_phone
from .heuristics import is_valid_dog_name


def import_selected_contacts(
    selectable_contacts: list[dict],
    selected_rows: list[int],
    overrides: dict[int, dict],
) -> tuple[list[CustomerOwner], list[ClientProfile], list[str]]:
    by_row = {c['row_number']: c for c in selectable_contacts}
    created_owners, created_dogs, errors = [], [], []

    for row_num in selected_rows:
        contact = by_row.get(row_num)
        if not contact or not contact['can_import']:
            errors.append(f'Row {row_num}: not found or cannot be imported.')
            continue

        override = overrides.get(row_num, {})
        dog_name = (override.get('dog_name') or contact['suggested_dog_name'] or '').strip()
        owner_name = (override.get('owner_name') or contact['suggested_owner_name'] or '').strip()
        email = contact['suggested_email'].strip().lower()
        phone = override.get('owner_phone') or contact['suggested_phone']

        try:
            phone = validate_phone(phone)
        except ValueError:
            phone = (phone or '').strip()

        if not email or not owner_name:
            errors.append(f'Row {row_num}: email and owner name are required.')
            continue

        owner, created = CustomerOwner.objects.get_or_create(
            owner_email=email,
            defaults={'owner_name': owner_name, 'owner_phone': phone},
        )
        if not created:
            owner.owner_name = owner_name
            owner.owner_phone = phone
            owner.save(update_fields=['owner_name', 'owner_phone', 'updated_at'])
        else:
            created_owners.append(owner)

        if is_valid_dog_name(dog_name, owner_name):
            if ClientProfile.objects.filter(owner_email__iexact=email, dog_name__iexact=dog_name).exists():
                errors.append(f'Row {row_num}: dog {dog_name} already exists.')
                continue

            note_parts = [contact['notes']] if contact['notes'] else []
            if contact['name_issues']:
                note_parts.append('Name flags: ' + '; '.join(contact['name_issues']))

            dog = ClientProfile.objects.create(
                dog_name=dog_name,
                owner_name=owner.owner_name,
                owner_email=owner.owner_email,
                owner_phone=owner.owner_phone,
                notes='\n'.join(note_parts).strip()[:2000],
                pipeline_stage=ClientProfile.PipelineStage.INQUIRY,
            )
            created_dogs.append(dog)

    return created_owners, created_dogs, errors