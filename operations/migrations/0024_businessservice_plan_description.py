from django.db import migrations, models


SEED_COPY = {
    'short_visit': {
        'summary': 'Up to 4 hours of care (not overnight).',
        'description': (
            'Short Visit covers a booked stay of up to 4 hours that is not an overnight. '
            'Your dog is cared for during the scheduled window with the same check-in and '
            'check-out process used for all stays. Overnight pricing rules do not apply.'
        ),
    },
    'daytime_visit': {
        'summary': 'Up to 12 hours of care (not overnight).',
        'description': (
            'Daytime Visit covers a booked stay of up to 12 hours that is not an overnight. '
            'Your dog is cared for during the scheduled window. If the stay crosses the '
            'overnight window or otherwise qualifies as overnight under Dad4dogs pricing rules, '
            'Overnight Stay applies instead.'
        ),
    },
    'overnight_stay': {
        'summary': 'Overnight or multi-day overnight boarding.',
        'description': (
            'Overnight Stay covers care when the booking crosses the overnight window '
            '(or otherwise qualifies as overnight under Dad4dogs pricing rules), including '
            'multi-day stays where each full 24-hour block is overnight care. '
            'Includes the scheduled boarding period with check-in and check-out at the booked times.'
        ),
    },
}


def backfill_descriptions(apps, schema_editor):
    BusinessService = apps.get_model('operations', 'BusinessService')
    for service in BusinessService.objects.all():
        copy = SEED_COPY.get(service.slug)
        if copy:
            service.summary = service.summary or copy['summary']
            if not (service.description or '').strip():
                service.description = copy['description']
        elif not (service.description or '').strip():
            service.description = (
                f'{service.name}: full service plan to be completed. '
                'Describe what is included, expectations, and boundaries for the customer.'
            )
        service.save(update_fields=['summary', 'description'])


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('operations', '0023_seed_default_business_services'),
    ]

    operations = [
        migrations.AddField(
            model_name='businessservice',
            name='summary',
            field=models.CharField(
                blank=True,
                help_text='Optional short blurb for lists and future booking pickers (customer-facing).',
                max_length=240,
            ),
        ),
        migrations.AddField(
            model_name='businessservice',
            name='description',
            field=models.TextField(
                blank=True,
                default='',
                help_text=(
                    'Full customer-facing service plan: what is included, expectations, and '
                    'boundaries. Plain text only.'
                ),
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='businessservice',
            name='staff_notes',
            field=models.TextField(
                blank=True,
                help_text=(
                    'Internal notes only — never show on customer emails, statements, or public pages.'
                ),
            ),
        ),
        migrations.RunPython(backfill_descriptions, noop_reverse),
        migrations.AlterField(
            model_name='businessservice',
            name='description',
            field=models.TextField(
                help_text=(
                    'Full customer-facing service plan: what is included, expectations, and '
                    'boundaries. Plain text only.'
                ),
            ),
        ),
    ]
