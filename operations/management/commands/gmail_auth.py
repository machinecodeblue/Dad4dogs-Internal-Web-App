import json

from django.conf import settings
from django.core.management.base import BaseCommand

from operations.services.gmail_paths import gmail_credentials_file, gmail_token_file
from operations.services.gmail_send import GMAIL_SEND_SCOPE, GmailSendError, send_gmail


class Command(BaseCommand):
    help = 'Check Gmail OAuth setup or send a test email.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--test',
            metavar='EMAIL',
            help='Send a test message to this address (uses live Gmail API).',
        )

    def handle(self, *args, **options):
        creds_path = gmail_credentials_file()
        token_path = gmail_token_file()

        self.stdout.write(f'OAuth folder: {settings.GMAIL_OAUTH_DIR}')
        self.stdout.write('')

        if not creds_path.exists():
            self.stderr.write(self.style.ERROR(f'Missing client secrets: {creds_path}'))
            self.stderr.write('Place your Google OAuth JSON in O-Auth Key/.')
            return

        try:
            creds_data = json.loads(creds_path.read_text(encoding='utf-8'))
        except json.JSONDecodeError:
            self.stderr.write(self.style.ERROR(f'Invalid JSON in {creds_path}'))
            return

        if 'installed' in creds_data:
            client_type = 'Desktop (installed)'
        elif 'web' in creds_data:
            client_type = 'Web — wrong type for local oauth_setup.py; create a Desktop OAuth client'
        else:
            client_type = 'Unknown'
        project_id = (
            creds_data.get('installed', {}).get('project_id')
            or creds_data.get('web', {}).get('project_id')
            or '?'
        )
        client_id = (
            creds_data.get('installed', {}).get('client_id')
            or creds_data.get('web', {}).get('client_id')
            or '?'
        )
        self.stdout.write(self.style.SUCCESS(f'Client secrets: {creds_path.name}'))
        self.stdout.write(f'  Type: {client_type}')
        self.stdout.write(f'  Project: {project_id}')
        self.stdout.write(f'  Client ID: {client_id}')
        self.stdout.write(f'  Scope required: {GMAIL_SEND_SCOPE}')
        self.stdout.write('')

        if not token_path.exists():
            self.stderr.write(self.style.WARNING(f'Token missing: {token_path}'))
            self.stderr.write('Run: python oauth_setup.py')
            self.stderr.write('Then sign in to Gmail in the browser and approve send access.')
            return

        try:
            token_data = json.loads(token_path.read_text(encoding='utf-8'))
        except json.JSONDecodeError:
            self.stderr.write(self.style.ERROR(f'Invalid JSON in {token_path}'))
            self.stderr.write('Delete token.json and run: python oauth_setup.py')
            return

        self.stdout.write(self.style.SUCCESS(f'Token: {token_path.name}'))
        self.stdout.write(f'  Has refresh token: {bool(token_data.get("refresh_token"))}')
        self.stdout.write(f'  Scopes: {token_data.get("scopes") or token_data.get("scope", "?")}')

        if not token_data.get('refresh_token'):
            self.stderr.write(self.style.WARNING(
                'No refresh token — delete token.json and re-run oauth_setup.py',
            ))

        test_to = (options.get('test') or '').strip()
        if not test_to:
            self.stdout.write('')
            self.stdout.write('OAuth files look present. To verify sending:')
            self.stdout.write('  python manage.py gmail_auth --test you@example.com')
            return

        try:
            result = send_gmail(
                subject='Dad4dogs Gmail test',
                body='If you received this, Gmail OAuth is working.',
                to=test_to,
            )
        except GmailSendError as exc:
            self.stderr.write(self.style.ERROR(f'Send failed: {exc}'))
            return

        self.stdout.write(self.style.SUCCESS(f'Test email sent to {test_to} (id: {result.get("id", "?")})'))