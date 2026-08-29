# Seed Meet & Greet / Initial Evaluation catalog rows; backfill intake M&G visits.

from decimal import Decimal

from django.db import migrations


INTAKE_SERVICES = [
    {
        'slug': 'meet_greet',
        'name': 'Meet & Greet',
        'base_rate': Decimal('0.00'),
        'capacity_exempt': True,
        'description': (
            '15-minute suitability visit. Free prerequisite before paperwork and evaluation. '
            'Does not count against daily boarding capacity.'
        ),
        'summary': '15-minute suitability visit (free)',
        'staff_notes': 'Suggested duration 15 minutes. Capacity exempt. Checkout fee $0.',
    },
    {
        'slug': 'initial_evaluation',
        'name': 'Initial Evaluation',
        'base_rate': Decimal('15.00'),
        'capacity_exempt': False,
        'description': (
            'Approximately 4-hour trial stay in the pack after Meet & Greet and paperwork. '
            'Flat $15 evaluation fee.'
        ),
        'summary': '~4h trial stay ($15)',
        'staff_notes': 'Suggested duration ~4 hours. Counts toward capacity. Not wired to intake yet.',
    },
]


def seed_intake_services(apps, schema_editor):
    Workspace = apps.get_model('operations', 'Workspace')
    BusinessService = apps.get_model('operations', 'BusinessService')
    Visit = apps.get_model('operations', 'Visit')

    for workspace in Workspace.objects.all():
        meet = None
        for row in INTAKE_SERVICES:
            service, _ = BusinessService.objects.get_or_create(
                tenant=workspace,
                slug=row['slug'],
                defaults={
                    'name': row['name'],
                    'target_category': 'DOG',
                    'rate_type': 'FLAT',
                    'base_rate': row['base_rate'],
                    'capacity_exempt': row['capacity_exempt'],
                    'is_active': True,
                    'description': row['description'],
                    'summary': row['summary'],
                    'staff_notes': row['staff_notes'],
                },
            )
            if row['slug'] == 'meet_greet':
                meet = service

        if meet is None:
            continue
        Visit.objects.filter(
            tenant=workspace,
            notes__icontains='Meet & Greet — intake',
        ).exclude(business_service=meet).update(business_service=meet)


def unseed_intake_services(apps, schema_editor):
    BusinessService = apps.get_model('operations', 'BusinessService')
    BusinessService.objects.filter(
        slug__in=[row['slug'] for row in INTAKE_SERVICES],
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('operations', '0025_visit_business_service'),
    ]

    operations = [
        migrations.RunPython(seed_intake_services, unseed_intake_services),
    ]
