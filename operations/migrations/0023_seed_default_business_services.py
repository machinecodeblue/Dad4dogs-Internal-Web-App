# Seed classic dog boarding offerings aligned with current pricing.py rates.

from decimal import Decimal

from django.db import migrations


DEFAULTS = [
    {
        'slug': 'short_visit',
        'name': 'Short Visit',
        'target_category': 'DOG',
        'rate_type': 'FLAT',
        'base_rate': Decimal('15.00'),
    },
    {
        'slug': 'daytime_visit',
        'name': 'Daytime Visit',
        'target_category': 'DOG',
        'rate_type': 'FLAT',
        'base_rate': Decimal('25.00'),
    },
    {
        'slug': 'overnight_stay',
        'name': 'Overnight Stay',
        'target_category': 'DOG',
        'rate_type': 'FLAT',
        'base_rate': Decimal('37.50'),
    },
]


def seed_services(apps, schema_editor):
    Workspace = apps.get_model('operations', 'Workspace')
    BusinessService = apps.get_model('operations', 'BusinessService')
    workspace, _ = Workspace.objects.get_or_create(
        slug='dad4dogs',
        defaults={'is_active': True},
    )
    for row in DEFAULTS:
        BusinessService.objects.get_or_create(
            tenant=workspace,
            slug=row['slug'],
            defaults={
                'name': row['name'],
                'target_category': row['target_category'],
                'rate_type': row['rate_type'],
                'base_rate': row['base_rate'],
                'is_active': True,
                'capacity_exempt': False,
            },
        )


def unseed_services(apps, schema_editor):
    BusinessService = apps.get_model('operations', 'BusinessService')
    Workspace = apps.get_model('operations', 'Workspace')
    workspace = Workspace.objects.filter(slug='dad4dogs').first()
    if not workspace:
        return
    BusinessService.objects.filter(
        tenant=workspace,
        slug__in=[row['slug'] for row in DEFAULTS],
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('operations', '0022_business_services_catalog'),
    ]

    operations = [
        migrations.RunPython(seed_services, unseed_services),
    ]
