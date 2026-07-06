from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.core.wsgi import get_wsgi_application


class Command(BaseCommand):
    help = 'Run the development server over HTTPS using mkcert certificates.'

    def add_arguments(self, parser):
        parser.add_argument(
            'addrport',
            nargs='?',
            default='127.0.0.1:9000',
            help='Optional port number, or ipaddr:port (default: 127.0.0.1:9000)',
        )
        parser.add_argument(
            '--cert-dir',
            default=None,
            help='Directory containing mkcert PEM files (default: <project>/certs)',
        )

    def handle(self, *args, **options):
        from werkzeug.serving import run_simple

        addr, port = self._parse_addrport(options['addrport'])
        cert_dir = Path(options['cert_dir'] or settings.BASE_DIR / 'certs')
        cert_file = cert_dir / 'localhost+2.pem'
        key_file = cert_dir / 'localhost+2-key.pem'

        if not cert_file.exists() or not key_file.exists():
            self.stderr.write(self.style.ERROR(
                f'Certificates not found in {cert_dir}.\n'
                'Run: .\\scripts\\setup-certs.ps1'
            ))
            return

        self.stdout.write(self.style.SUCCESS(
            f'Starting HTTPS development server at https://{addr}:{port}/'
        ))
        self.stdout.write('Quit the server with CTRL-BREAK.')

        # Match Django runserver: serve /static/ from app packages in DEBUG.
        from django.contrib.staticfiles.handlers import StaticFilesHandler

        application = StaticFilesHandler(get_wsgi_application())
        run_simple(
            addr,
            port,
            application,
            use_reloader=True,
            use_debugger=True,
            ssl_context=(str(cert_file), str(key_file)),
            threaded=True,
        )

    def _parse_addrport(self, addrport: str) -> tuple[str, int]:
        if ':' in addrport:
            addr, port = addrport.rsplit(':', 1)
            return addr, int(port)
        return '127.0.0.1', int(addrport)