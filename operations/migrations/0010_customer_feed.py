from django.db import migrations, models

import operations.services.feed_slugs as feed_slugs


def backfill_feed_credentials(apps, schema_editor):
    ClientProfile = apps.get_model('operations', 'ClientProfile')
    used_secrets = set(
        ClientProfile.objects.exclude(feed_secret='')
        .exclude(feed_secret__isnull=True)
        .values_list('feed_secret', flat=True)
    )
    for client in ClientProfile.objects.all():
        changed = False
        if not client.feed_dog_slug:
            client.feed_dog_slug = feed_slugs.dog_slug_from_name(client.dog_name)
            changed = True
        if not client.feed_secret:
            for _ in range(40):
                candidate = feed_slugs.generate_feed_secret()
                if candidate not in used_secrets:
                    client.feed_secret = candidate
                    used_secrets.add(candidate)
                    changed = True
                    break
        if changed:
            client.save(update_fields=['feed_secret', 'feed_dog_slug', 'updated_at'])


class Migration(migrations.Migration):

    dependencies = [
        ('operations', '0009_timeline_media_asset'),
    ]

    operations = [
        migrations.CreateModel(
            name='FeedAccessLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('visitor_id', models.CharField(max_length=36)),
                ('user_agent', models.CharField(blank=True, max_length=500)),
                ('accessed_at', models.DateTimeField(auto_now_add=True)),
                ('client', models.ForeignKey(on_delete=models.deletion.CASCADE, related_name='feed_access_logs', to='operations.clientprofile')),
            ],
            options={
                'ordering': ['-accessed_at'],
            },
        ),
        migrations.AddField(
            model_name='clientprofile',
            name='feed_dog_slug',
            field=models.CharField(blank=True, help_text='URL segment from dog name (e.g. lulu).', max_length=80),
        ),
        migrations.AddField(
            model_name='clientprofile',
            name='feed_secret',
            field=models.CharField(blank=True, help_text='Speakable secret for customer feed URL (e.g. squeakytiki).', max_length=40, null=True, unique=True),
        ),
        migrations.AddIndex(
            model_name='feedaccesslog',
            index=models.Index(fields=['client', 'accessed_at'], name='operations__client__8d2f0a_idx'),
        ),
        migrations.AddIndex(
            model_name='feedaccesslog',
            index=models.Index(fields=['client', 'visitor_id'], name='operations__client__f0a2c1_idx'),
        ),
        migrations.RunPython(backfill_feed_credentials, migrations.RunPython.noop),
    ]