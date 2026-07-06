from django.db import migrations, models

import operations.services.feed_slugs as feed_slugs


def backfill_share_tokens(apps, schema_editor):
    SharedMediaLink = apps.get_model('operations', 'SharedMediaLink')
    used = set(
        SharedMediaLink.objects.exclude(share_token='')
        .exclude(share_token__isnull=True)
        .values_list('share_token', flat=True)
    )
    for link in SharedMediaLink.objects.all():
        if link.share_token:
            continue
        for _ in range(40):
            candidate = feed_slugs.generate_share_token()
            if candidate not in used:
                link.share_token = candidate
                used.add(candidate)
                link.save(update_fields=['share_token'])
                break


class Migration(migrations.Migration):

    dependencies = [
        ('operations', '0011_feed_interactions'),
    ]

    operations = [
        migrations.AddField(
            model_name='sharedmedialink',
            name='share_token',
            field=models.CharField(
                blank=True,
                help_text='Public URL key — /feed/share/<share_token>/',
                max_length=24,
                null=True,
                unique=True,
            ),
        ),
        migrations.RunPython(backfill_share_tokens, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='sharedmedialink',
            name='share_token',
            field=models.CharField(
                blank=True,
                help_text='Public URL key — /feed/share/<share_token>/',
                max_length=24,
                unique=True,
            ),
        ),
    ]