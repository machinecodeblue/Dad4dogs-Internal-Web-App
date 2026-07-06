import os
from pathlib import Path

from django.conf import settings


def gmail_oauth_dir() -> Path:
    return Path(settings.GMAIL_OAUTH_DIR)


def gmail_credentials_file() -> Path:
    """Resolve OAuth client secrets JSON (credentials.json or client_secret*.json)."""
    override = os.environ.get('GMAIL_CREDENTIALS_FILE', '').strip()
    if override:
        return Path(override)

    oauth_dir = gmail_oauth_dir()
    credentials = oauth_dir / 'credentials.json'
    if credentials.exists():
        return credentials

    client_secrets = sorted(
        oauth_dir.glob('client_secret*.json'),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if client_secrets:
        return client_secrets[0]

    return credentials


def gmail_token_file() -> Path:
    override = os.environ.get('GMAIL_TOKEN_FILE', '').strip()
    if override:
        return Path(override)
    return gmail_oauth_dir() / 'token.json'