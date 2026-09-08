"""Flush and load a full demo dataset (25 owners, 30 dogs, varied visits)."""

from django.core.management.base import BaseCommand

from operations.services.context_tenant import get_active_workspace
from operations.services.demo_seed import (
    flush_demo_data,
    format_seed_summary,
    seed_owners_and_dogs,
    seed_visits,
)


class Command(BaseCommand):
    help = (
        'Delete customer/visit data for the active workspace and load demo data: '
        '25 owners, 30 dogs, and scheduling scenarios.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--no-input',
            action='store_true',
            help='Do not prompt for confirmation.',
        )
        parser.add_argument(
            '--flush-only',
            action='store_true',
            help='Wipe customer/visit data without reseeding.',
        )

    def handle(self, *args, **options):
        workspace = get_active_workspace()
        self.stdout.write(
            self.style.WARNING(
                f'This will DELETE owners, dogs, visits, and related rows '
                f'for workspace "{workspace.slug}". '
                f'Business settings and service catalog are kept.'
            )
        )
        if not options['no_input']:
            confirm = input('Type "yes" to continue: ').strip()
            if confirm != 'yes':
                self.stdout.write(self.style.NOTICE('Aborted.'))
                return

        deleted = flush_demo_data()
        self.stdout.write('Flushed:')
        for label, count in deleted.items():
            if count:
                self.stdout.write(f'  {label}: {count}')

        if options['flush_only']:
            self.stdout.write(self.style.SUCCESS('Flush complete (--flush-only).'))
            return

        bundle = seed_owners_and_dogs()
        visit_counts = seed_visits(bundle)
        self.stdout.write(format_seed_summary(bundle, visit_counts))
        self.stdout.write(self.style.SUCCESS('seed_demo_data finished.'))
