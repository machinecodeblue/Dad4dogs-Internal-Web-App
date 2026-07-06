from django.core.management.base import BaseCommand

from operations.services.statements import generate_weekly_statements, format_statement_email


class Command(BaseCommand):
    help = 'Generate weekly account statements for all clients with completed visits.'

    def handle(self, *args, **options):
        statements = generate_weekly_statements()
        if not statements:
            self.stdout.write('No completed visits found for this week.')
            return

        for statement in statements:
            self.stdout.write(
                f'{statement.client.dog_name}: ${statement.total_amount} CAD — queued',
            )
            self.stdout.write(format_statement_email(statement))
            self.stdout.write('-' * 40)

        self.stdout.write(self.style.SUCCESS(f'Generated {len(statements)} statement(s).'))