from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('operations', '0018_backfill_owners_and_feed_credentials'),
    ]

    operations = [
        migrations.AddField(
            model_name='clientprofile',
            name='is_hidden',
            field=models.BooleanField(
                default=False,
                help_text='Hidden dogs stay on file with visits and photos, but leave the client list.',
            ),
        ),
    ]
