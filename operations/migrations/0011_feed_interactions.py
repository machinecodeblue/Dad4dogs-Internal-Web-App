import uuid

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('operations', '0010_customer_feed'),
    ]

    operations = [
        migrations.CreateModel(
            name='MediaReaction',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('visitor_id', models.CharField(help_text='Anonymous browser ID from dad4dogs_feed_vid cookie.', max_length=36)),
                ('emoji', models.CharField(choices=[('like', '👍'), ('love', '❤️'), ('haha', '😂'), ('wow', '😮'), ('sad', '😢')], max_length=10)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('media_asset', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='reactions', to='operations.timelinemediaasset')),
            ],
        ),
        migrations.CreateModel(
            name='MediaComment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('visitor_id', models.CharField(max_length=36)),
                ('display_name', models.CharField(default='Guest', max_length=80)),
                ('text', models.TextField()),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('client', models.ForeignKey(help_text='Dog feed where the comment was posted.', on_delete=django.db.models.deletion.CASCADE, related_name='feed_comments', to='operations.clientprofile')),
                ('media_asset', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='comments', to='operations.timelinemediaasset')),
            ],
            options={
                'ordering': ['created_at'],
            },
        ),
        migrations.CreateModel(
            name='SharedMediaLink',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('view_count', models.PositiveIntegerField(default=0)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('client', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='shared_media_links', to='operations.clientprofile')),
                ('media_asset', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='share_links', to='operations.timelinemediaasset')),
            ],
        ),
        migrations.AddConstraint(
            model_name='mediareaction',
            constraint=models.UniqueConstraint(fields=('media_asset', 'visitor_id'), name='unique_reaction_per_visitor_per_asset'),
        ),
        migrations.AddConstraint(
            model_name='sharedmedialink',
            constraint=models.UniqueConstraint(fields=('media_asset', 'client'), name='unique_share_link_per_asset_per_client'),
        ),
    ]