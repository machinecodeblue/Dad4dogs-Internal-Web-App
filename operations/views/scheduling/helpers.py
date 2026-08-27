from datetime import datetime

from django.core.exceptions import ValidationError
from django.utils import timezone


def apply_visit_form_errors(form, error: ValidationError):
    if hasattr(error, 'message_dict'):
        for field, errs in error.message_dict.items():
            for err in errs:
                form.add_error(field if field in form.fields else None, err)
    else:
        form.add_error(None, '; '.join(error.messages))


def form_error_message(form) -> str:
    """Flash-friendly form errors — labels and sentences, not as_text() asterisks."""
    parts = [str(err) for err in form.non_field_errors()]
    for name, field in form.fields.items():
        if name not in form.errors:
            continue
        label = field.label or name.replace('_', ' ')
        for err in form.errors[name]:
            parts.append(f'{label}: {err}')
    return '; '.join(parts) or 'Please check the form and try again.'


def parse_local_datetime_input(value: str):
    """Parse an HTML datetime-local value as America/Toronto-aware."""
    text = (value or '').strip()
    if not text:
        raise ValidationError('Enter a date and time.')
    for fmt in ('%Y-%m-%dT%H:%M', '%Y-%m-%dT%H:%M:%S'):
        try:
            naive = datetime.strptime(text, fmt)
            break
        except ValueError:
            naive = None
    else:
        raise ValidationError('Could not understand that date and time.')
    if timezone.is_naive(naive):
        return timezone.make_aware(naive, timezone.get_current_timezone())
    return timezone.localtime(naive)