from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('operations', '0005_visit_series'),
    ]

    operations = [
        migrations.AddField(
            model_name='visit',
            name='confirmation_email_sent_at',
            field=models.DateTimeField(
                blank=True,
                help_text='When the customer was emailed this booking confirmation.',
                null=True,
            ),
        ),
    ]