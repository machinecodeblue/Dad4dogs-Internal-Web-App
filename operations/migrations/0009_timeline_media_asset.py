import django.db.models.deletion
from django.db import migrations, models

import operations.models.scheduling


def migrate_timeline_events_to_assets(apps, schema_editor):
    VisitTimelineEvent = apps.get_model('operations', 'VisitTimelineEvent')
    TimelineMediaAsset = apps.get_model('operations', 'TimelineMediaAsset')

    for event in VisitTimelineEvent.objects.all():
        asset = TimelineMediaAsset.objects.create(
            media_type=event.media_type,
            photo_high_res=event.photo_high_res,
            photo_thumbnail=event.photo_thumbnail,
            video_file=event.video_file,
            caption_notes=event.caption_notes,
            latitude=event.latitude,
            longitude=event.longitude,
            location_used_fallback=event.location_used_fallback,
            location_fallback_label=event.location_fallback_label,
            captured_at=event.created_at,
            original_visit_id=event.visit_id,
        )
        event.media_asset_id = asset.pk
        event.shared_at = event.created_at
        event.save(update_fields=['media_asset_id', 'shared_at'])


class Migration(migrations.Migration):

    dependencies = [
        ('operations', '0008_visit_timeline_event'),
    ]

    operations = [
        migrations.CreateModel(
            name='TimelineMediaAsset',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('media_type', models.CharField(choices=[('photo', 'Photo'), ('video', 'Video')], max_length=10)),
                ('photo_high_res', models.ImageField(blank=True, help_text='Uncompressed master image for customer printing.', upload_to=operations.models.scheduling.timeline_asset_upload_path)),
                ('photo_thumbnail', models.ImageField(blank=True, help_text='Web-optimized WebP thumbnail for timeline display.', upload_to=operations.models.scheduling.timeline_asset_upload_path)),
                ('video_file', models.FileField(blank=True, help_text='Gallery-selected video (no live capture).', upload_to=operations.models.scheduling.timeline_asset_upload_path)),
                ('caption_notes', models.TextField(blank=True)),
                ('latitude', models.DecimalField(decimal_places=6, max_digits=9)),
                ('longitude', models.DecimalField(decimal_places=6, max_digits=9)),
                ('location_used_fallback', models.BooleanField(default=False)),
                ('location_fallback_label', models.CharField(blank=True, max_length=300)),
                ('captured_at', models.DateTimeField(help_text='Exact capture/upload time — preserved when forwarded.', editable=False)),
                ('original_visit', models.ForeignKey(help_text='First visit this moment was logged against.', on_delete=django.db.models.deletion.PROTECT, related_name='originated_timeline_assets', to='operations.visit')),
            ],
            options={
                'ordering': ['-captured_at'],
            },
        ),
        migrations.AddField(
            model_name='visittimelineevent',
            name='media_asset',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='visit_links', to='operations.timelinemediaasset'),
        ),
        migrations.AddField(
            model_name='visittimelineevent',
            name='shared_at',
            field=models.DateTimeField(editable=False, null=True),
        ),
        migrations.AddField(
            model_name='visittimelineevent',
            name='source_event',
            field=models.ForeignKey(blank=True, help_text="Set when this row was forwarded from another dog's timeline.", null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='forwarded_copies', to='operations.visittimelineevent'),
        ),
        migrations.RunPython(migrate_timeline_events_to_assets, migrations.RunPython.noop),
        migrations.RemoveField(model_name='visittimelineevent', name='caption_notes'),
        migrations.RemoveField(model_name='visittimelineevent', name='created_at'),
        migrations.RemoveField(model_name='visittimelineevent', name='latitude'),
        migrations.RemoveField(model_name='visittimelineevent', name='location_fallback_label'),
        migrations.RemoveField(model_name='visittimelineevent', name='location_used_fallback'),
        migrations.RemoveField(model_name='visittimelineevent', name='longitude'),
        migrations.RemoveField(model_name='visittimelineevent', name='media_type'),
        migrations.RemoveField(model_name='visittimelineevent', name='photo_high_res'),
        migrations.RemoveField(model_name='visittimelineevent', name='photo_thumbnail'),
        migrations.RemoveField(model_name='visittimelineevent', name='video_file'),
        migrations.AlterField(
            model_name='visittimelineevent',
            name='media_asset',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='visit_links', to='operations.timelinemediaasset'),
        ),
        migrations.AlterField(
            model_name='visittimelineevent',
            name='shared_at',
            field=models.DateTimeField(auto_now_add=True, editable=False, help_text='When this moment was attached to this visit.'),
        ),
        migrations.AlterModelOptions(
            name='visittimelineevent',
            options={'ordering': ['-media_asset__captured_at', '-shared_at']},
        ),
        migrations.AddConstraint(
            model_name='visittimelineevent',
            constraint=models.UniqueConstraint(fields=('visit', 'media_asset'), name='unique_timeline_asset_per_visit'),
        ),
    ]