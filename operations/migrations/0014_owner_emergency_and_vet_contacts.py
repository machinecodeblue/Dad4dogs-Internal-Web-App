from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('operations', '0013_rename_operations__client__8d2f0a_idx_operations__client__17dcdd_idx_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='customerowner',
            name='owner_salutation',
            field=models.CharField(
                blank=True,
                help_text='Pronouns or salutation for statements and waivers (e.g. Ms., they/them).',
                max_length=40,
            ),
        ),
        migrations.AddField(
            model_name='customerowner',
            name='home_address',
            field=models.TextField(
                blank=True,
                help_text='Physical home address for records, insurance, and emergency drop-off.',
            ),
        ),
        migrations.AddField(
            model_name='customerowner',
            name='emergency_contact_name',
            field=models.CharField(blank=True, max_length=200),
        ),
        migrations.AddField(
            model_name='customerowner',
            name='emergency_contact_phone',
            field=models.CharField(blank=True, max_length=30),
        ),
        migrations.AddField(
            model_name='customerowner',
            name='emergency_contact_relationship',
            field=models.CharField(
                blank=True,
                help_text='e.g. Neighbor with house key, Aunt across town.',
                max_length=120,
            ),
        ),
        migrations.AddField(
            model_name='customerowner',
            name='authorized_pickup_names',
            field=models.TextField(
                blank=True,
                help_text='One name per line — individuals allowed to take any dog home.',
            ),
        ),
        migrations.AddField(
            model_name='clientprofile',
            name='vet_clinic_name',
            field=models.CharField(blank=True, max_length=200),
        ),
        migrations.AddField(
            model_name='clientprofile',
            name='vet_name',
            field=models.CharField(blank=True, max_length=200),
        ),
        migrations.AddField(
            model_name='clientprofile',
            name='vet_clinic_phone',
            field=models.CharField(blank=True, max_length=30),
        ),
        migrations.AddField(
            model_name='clientprofile',
            name='emergency_vet_clinic',
            field=models.CharField(
                blank=True,
                help_text='Preferred 24-hour emergency hospital when regular clinic is closed.',
                max_length=200,
            ),
        ),
        migrations.AddField(
            model_name='clientprofile',
            name='emergency_vet_phone',
            field=models.CharField(blank=True, max_length=30),
        ),
        migrations.AddField(
            model_name='clientprofile',
            name='vet_care_authorization',
            field=models.TextField(
                blank=True,
                help_text='Dollar cap or directive for lifesaving triage before owner contact.',
            ),
        ),
        migrations.AlterField(
            model_name='customerowner',
            name='owner_phone',
            field=models.CharField(
                blank=True,
                help_text='Primary mobile — required for real-time alerts.',
                max_length=30,
            ),
        ),
    ]