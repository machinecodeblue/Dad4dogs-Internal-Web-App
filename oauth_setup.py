"""
One-time Gmail OAuth setup for Dad4dogs.

Prerequisites:
  1. OAuth client JSON is in the O-Auth Key/ folder (credentials.json or client_secret*.json).
  2. pip install -r requirements.txt
  3. python oauth_setup.py

A browser window opens — sign in to Gmail and approve send access.
Creates token.json in O-Auth Key/.
"""
import os
import sys
from pathlib import Path

# Allow running before Django is configured.
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django

django.setup()

from google_auth_oauthlib.flow import InstalledAppFlow

from operations.services.gmail_paths import gmail_credentials_file, gmail_token_file

GMAIL_SEND_SCOPE = 'https://www.googleapis.com/auth/gmail.send'


def main():
    credentials_file = gmail_credentials_file()
    token_file = gmail_token_file()

    if not credentials_file.exists():
        raise SystemExit(
            f'OAuth client file not found.\n'
            f'Expected: {credentials_file}\n'
            f'Place your Google client JSON in the O-Auth Key/ folder.',
        )

    import json

    try:
        creds_data = json.loads(credentials_file.read_text(encoding='utf-8'))
    except json.JSONDecodeError as exc:
        raise SystemExit(f'Invalid JSON in {credentials_file}: {exc}') from exc

    if 'web' in creds_data and 'installed' not in creds_data:
        raise SystemExit(
            'This OAuth client is type "Web", not "Desktop".\n'
            'In Google Cloud Console → APIs & Services → Credentials,\n'
            'create an OAuth 2.0 Client ID of type "Desktop app", download JSON,\n'
            'and place it in O-Auth Key/.',
        )

    print('Opening browser for Gmail sign-in…')
    print(f'  Client: {credentials_file.name}')
    print(f'  Scope:  {GMAIL_SEND_SCOPE}')
    print('  Approve access, then return here.')
    print('')

    flow = InstalledAppFlow.from_client_secrets_file(
        str(credentials_file),
        scopes=[GMAIL_SEND_SCOPE],
    )
    creds = flow.run_local_server(
        port=0,
        prompt='consent',
        access_type='offline',
    )
    if not creds.refresh_token:
        raise SystemExit(
            'Google did not return a refresh token.\n'
            'Revoke app access at https://myaccount.google.com/permissions\n'
            'then run python oauth_setup.py again.',
        )

    token_file.parent.mkdir(parents=True, exist_ok=True)
    token_file.write_text(creds.to_json(), encoding='utf-8')
    print('Gmail OAuth complete.')
    print(f'  Token saved: {token_file}')
    print('Verify with: python manage.py gmail_auth --test your@email.com')


if __name__ == '__main__':
    main()