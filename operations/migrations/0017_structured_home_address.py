from django.db import migrations, models


def copy_legacy_addresses(apps, schema_editor):
    CustomerOwner = apps.get_model('operations', 'CustomerOwner')
    from operations.services.addresses import parse_legacy_address

    for owner in CustomerOwner.objects.exclude(home_address='').iterator():
        parsed = parse_legacy_address(owner.home_address)
        if not any(parsed.values()):
            continue
        owner.address_street = parsed['street']
        owner.address_unit = parsed['unit']
        owner.address_city = parsed['city']
        owner.address_province = parsed['province']
        owner.address_postal_code = parsed['postal']
        owner.save(update_fields=[
            'address_street',
            'address_unit',
            'address_city',
            'address_province',
            'address_postal_code',
        ])


class Migration(migrations.Migration):

    dependencies = [
        ('operations', '0016_visit_hot_lookup_indexes'),
    ]

    operations = [
        migrations.AddField(
            model_name='customerowner',
            name='address_city',
            field=models.CharField(blank=True, max_length=100),
        ),
        migrations.AddField(
            model_name='customerowner',
            name='address_postal_code',
            field=models.CharField(
                blank=True,
                help_text='Canadian postal code (e.g. N6B 1G2).',
                max_length=7,
            ),
        ),
        migrations.AddField(
            model_name='customerowner',
            name='address_province',
            field=models.CharField(
                blank=True,
                choices=[
                    ('AB', 'Alberta'),
                    ('BC', 'British Columbia'),
                    ('MB', 'Manitoba'),
                    ('NB', 'New Brunswick'),
                    ('NL', 'Newfoundland and Labrador'),
                    ('NS', 'Nova Scotia'),
                    ('NT', 'Northwest Territories'),
                    ('NU', 'Nunavut'),
                    ('ON', 'Ontario'),
                    ('PE', 'Prince Edward Island'),
                    ('QC', 'Quebec'),
                    ('SK', 'Saskatchewan'),
                    ('YT', 'Yukon'),
                ],
                help_text='Two-letter province or territory code.',
                max_length=2,
            ),
        ),
        migrations.AddField(
            model_name='customerowner',
            name='address_street',
            field=models.CharField(
                blank=True,
                help_text='Street number and name.',
                max_length=200,
            ),
        ),
        migrations.AddField(
            model_name='customerowner',
            name='address_unit',
            field=models.CharField(
                blank=True,
                help_text='Unit, apartment, or suite — optional.',
                max_length=40,
            ),
        ),
        migrations.AlterField(
            model_name='customerowner',
            name='home_address',
            field=models.TextField(
                blank=True,
                help_text='Formatted or legacy free-text home address. Rebuilt from structured fields on save.',
            ),
        ),
        migrations.RunPython(copy_legacy_addresses, migrations.RunPython.noop),
    ]
