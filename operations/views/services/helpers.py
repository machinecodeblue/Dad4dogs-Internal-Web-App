def form_error_message(form) -> str:
    """Flatten form errors for a flash message."""
    parts = []
    for field, errors in form.errors.items():
        label = 'Form' if field == '__all__' else field.replace('_', ' ')
        for error in errors:
            parts.append(f'{label}: {error}')
    return '; '.join(parts) if parts else 'Please correct the errors below.'
