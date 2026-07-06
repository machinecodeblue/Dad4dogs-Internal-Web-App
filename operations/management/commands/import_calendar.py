from pathlib import Path

from django.core.management.base import BaseCommand

from operations.services.gmail_sync import parse_ics_file


class Command(BaseCommand):
    help = 'Import Google Calendar events from an .ics file for pending review.'

    def add_arguments(self, parser):
        parser.add_argument('ics_path', type=str, help='Path to the .ics file to import')

    def handle(self, *args, **options):
        path = Path(options['ics_path'])
        if not path.exists():
            self.stderr.write(f'File not found: {path}')
            return

        created = parse_ics_file(path)
        self.stdout.write(self.style.SUCCESS(f'Imported {len(created)} new calendar event(s).'))