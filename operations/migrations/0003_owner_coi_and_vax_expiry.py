from datetime import timedelta

from django.db import migrations, models
from django.utils import timezone


def migrate_owners_and_coi(apps, schema_editor):
    ClientProfile = apps.get_model('operations', 'ClientProfile')
    CustomerOwner = apps.get_model('operations', 'CustomerOwner')

    seen_emails = set()
    for client in ClientProfile.objects.order_by('pk'):
        email = client.owner_email.lower().strip()
        if email in seen_emails:
            owner = CustomerOwner.objects.get(owner_email=email)
            continue
        seen_emails.add(email)

        owner, _ = CustomerOwner.objects.get_or_create(
            owner_email=email,
            defaults={
                'owner_name': client.owner_name,
                'owner_phone': client.owner_phone,
            },
        )
        if client.coi_confirmed_received:
            owner.coi_confirmed_received = True
            owner.coi_confirmed_at = client.coi_confirmed_at
            owner.coi_sent_at = client.coi_sent_at or client.coi_confirmed_at
            owner.save()
        elif client.coi_sent_at and not owner.coi_sent_at:
            owner.coi_sent_at = client.coi_sent_at
            owner.save()


def set_vaccination_expiry(apps, schema_editor):
    VaccinationRecord = apps.get_model('operations', 'VaccinationRecord')
    for record in VaccinationRecord.objects.all():
        record.expires_at = record.received_at + timedelta(days=365)
        record.save(update_fields=['expires_at'])


class Migration(migrations.Migration):

    dependencies = [
        ('operations', '0002_clientprofile_coi_confirmed_at_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='CustomerOwner',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('owner_email', models.EmailField(max_length=254, unique=True)),
                ('owner_name', models.CharField(max_length=200)),
                ('owner_phone', models.CharField(blank=True, max_length=30)),
                ('coi_sent_at', models.DateTimeField(blank=True, null=True)),
                ('coi_confirmed_received', models.BooleanField(default=False)),
                ('coi_confirmed_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'customer (owner)',
                'verbose_name_plural': 'customers (owners)',
                'ordering': ['owner_name'],
            },
        ),
        migrations.RunPython(migrate_owners_and_coi, migrations.RunPython.noop),
        migrations.AddField(
            model_name='vaccinationrecord',
            name='expires_at',
            field=models.DateField(
                default=timezone.localdate,
                help_text='Date vaccinations expire per veterinarian papers.',
            ),
            preserve_default=False,
        ),
        migrations.RunPython(set_vaccination_expiry, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name='clientprofile',
            name='coi_confirmed_at',
        ),
        migrations.RemoveField(
            model_name='clientprofile',
            name='coi_confirmed_received',
        ),
        migrations.RemoveField(
            model_name='clientprofile',
            name='coi_sent_at',
        ),
        migrations.AlterField(
            model_name='vaccinationrecord',
            name='received_at',
            field=models.DateField(
                default=timezone.localdate,
                help_text='Date vaccination papers were received.',
            ),
        ),
    ]