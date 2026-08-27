# Multi-tenant Workspace + CapacitySettings + tenant FKs (Option B Phase 1)

import django.core.validators
import django.db.models.deletion
import uuid
from django.db import migrations, models


def forwards_seed_workspace(apps, schema_editor):
    Workspace = apps.get_model('operations', 'Workspace')
    BusinessProfile = apps.get_model('operations', 'BusinessProfile')
    CapacitySettings = apps.get_model('operations', 'CapacitySettings')

    workspace, _ = Workspace.objects.get_or_create(
        slug='dad4dogs',
        defaults={'is_active': True},
    )

    profile = BusinessProfile.objects.order_by('pk').first()
    standard = 8
    ceiling = 10
    if profile is not None:
        # Capacity columns still present during this RunPython step.
        standard = getattr(profile, 'standard_capacity', None) or 8
        ceiling = getattr(profile, 'insurance_ceiling', None) or 10
        if ceiling < standard:
            ceiling = standard
        if profile.workspace_id is None:
            profile.workspace = workspace
            profile.save(update_fields=['workspace'])
    else:
        BusinessProfile.objects.create(
            workspace=workspace,
            business_name='Dad4dogs',
        )

    CapacitySettings.objects.get_or_create(
        workspace=workspace,
        defaults={
            'standard_capacity': standard,
            'insurance_ceiling': ceiling,
        },
    )

    tenant_models = [
        'CustomerOwner',
        'ClientProfile',
        'VaccinationRecord',
        'FeedAccessLog',
        'VisitSeries',
        'Visit',
        'TimelineMediaAsset',
        'VisitTimelineEvent',
        'MediaReaction',
        'MediaComment',
        'SharedMediaLink',
        'PendingCalendarEvent',
        'AccountStatement',
    ]
    for name in tenant_models:
        Model = apps.get_model('operations', name)
        Model.objects.filter(tenant__isnull=True).update(tenant=workspace)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('operations', '0020_businessprofile_capacity_limits'),
    ]

    operations = [
        migrations.CreateModel(
            name='Workspace',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('slug', models.SlugField(max_length=100, unique=True)),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'workspace',
                'verbose_name_plural': 'workspaces',
            },
        ),
        migrations.CreateModel(
            name='CapacitySettings',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('standard_capacity', models.PositiveSmallIntegerField(
                    default=8,
                    help_text='Comfortable daily dog count. Days above this show a warning.',
                    validators=[
                        django.core.validators.MinValueValidator(1),
                        django.core.validators.MaxValueValidator(50),
                    ],
                )),
                ('insurance_ceiling', models.PositiveSmallIntegerField(
                    default=10,
                    help_text='Hard maximum for new bookings (insurance). Cannot schedule above this.',
                    validators=[
                        django.core.validators.MinValueValidator(1),
                        django.core.validators.MaxValueValidator(50),
                    ],
                )),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('workspace', models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='capacity_settings',
                    to='operations.workspace',
                )),
            ],
            options={
                'verbose_name': 'capacity settings',
                'verbose_name_plural': 'capacity settings',
            },
        ),
        migrations.RemoveConstraint(
            model_name='clientprofile',
            name='unique_owner_email_dog_name',
        ),
        migrations.RemoveIndex(
            model_name='visit',
            name='visit_scheduled_start_idx',
        ),
        migrations.RemoveIndex(
            model_name='visit',
            name='visit_scheduled_end_idx',
        ),
        migrations.RemoveIndex(
            model_name='visit',
            name='visit_status_idx',
        ),
        migrations.AlterField(
            model_name='customerowner',
            name='owner_email',
            field=models.EmailField(max_length=254),
        ),
        migrations.AddField(
            model_name='businessprofile',
            name='workspace',
            field=models.OneToOneField(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='profile',
                to='operations.workspace',
            ),
        ),
        migrations.AddField(
            model_name='accountstatement',
            name='tenant',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='%(app_label)s_%(class)s_set',
                to='operations.workspace',
            ),
        ),
        migrations.AddField(
            model_name='clientprofile',
            name='tenant',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='%(app_label)s_%(class)s_set',
                to='operations.workspace',
            ),
        ),
        migrations.AddField(
            model_name='customerowner',
            name='tenant',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='%(app_label)s_%(class)s_set',
                to='operations.workspace',
            ),
        ),
        migrations.AddField(
            model_name='feedaccesslog',
            name='tenant',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='%(app_label)s_%(class)s_set',
                to='operations.workspace',
            ),
        ),
        migrations.AddField(
            model_name='mediacomment',
            name='tenant',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='%(app_label)s_%(class)s_set',
                to='operations.workspace',
            ),
        ),
        migrations.AddField(
            model_name='mediareaction',
            name='tenant',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='%(app_label)s_%(class)s_set',
                to='operations.workspace',
            ),
        ),
        migrations.AddField(
            model_name='pendingcalendarevent',
            name='tenant',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='%(app_label)s_%(class)s_set',
                to='operations.workspace',
            ),
        ),
        migrations.AddField(
            model_name='sharedmedialink',
            name='tenant',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='%(app_label)s_%(class)s_set',
                to='operations.workspace',
            ),
        ),
        migrations.AddField(
            model_name='timelinemediaasset',
            name='tenant',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='%(app_label)s_%(class)s_set',
                to='operations.workspace',
            ),
        ),
        migrations.AddField(
            model_name='vaccinationrecord',
            name='tenant',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='%(app_label)s_%(class)s_set',
                to='operations.workspace',
            ),
        ),
        migrations.AddField(
            model_name='visit',
            name='tenant',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='%(app_label)s_%(class)s_set',
                to='operations.workspace',
            ),
        ),
        migrations.AddField(
            model_name='visitseries',
            name='tenant',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='%(app_label)s_%(class)s_set',
                to='operations.workspace',
            ),
        ),
        migrations.AddField(
            model_name='visittimelineevent',
            name='tenant',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='%(app_label)s_%(class)s_set',
                to='operations.workspace',
            ),
        ),
        migrations.RunPython(forwards_seed_workspace, noop_reverse),
        migrations.RemoveField(
            model_name='businessprofile',
            name='insurance_ceiling',
        ),
        migrations.RemoveField(
            model_name='businessprofile',
            name='singleton_key',
        ),
        migrations.RemoveField(
            model_name='businessprofile',
            name='standard_capacity',
        ),
        migrations.AddIndex(
            model_name='visit',
            index=models.Index(fields=['tenant', 'scheduled_start'], name='visit_tenant_start_idx'),
        ),
        migrations.AddIndex(
            model_name='visit',
            index=models.Index(fields=['tenant', 'scheduled_end'], name='visit_tenant_end_idx'),
        ),
        migrations.AddIndex(
            model_name='visit',
            index=models.Index(fields=['tenant', 'status'], name='visit_tenant_status_idx'),
        ),
        migrations.AddConstraint(
            model_name='clientprofile',
            constraint=models.UniqueConstraint(
                fields=('tenant', 'owner_email', 'dog_name'),
                name='unique_tenant_owner_email_dog_name',
            ),
        ),
        migrations.AddConstraint(
            model_name='customerowner',
            constraint=models.UniqueConstraint(
                fields=('tenant', 'owner_email'),
                name='unique_tenant_customer_owner_email',
            ),
        ),
    ]
