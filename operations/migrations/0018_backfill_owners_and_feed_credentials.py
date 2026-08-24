from django.db import migrations


def backfill_owners_and_feed(apps, schema_editor):
    ClientProfile = apps.get_model('operations', 'ClientProfile')
    CustomerOwner = apps.get_model('operations', 'CustomerOwner')
    from operations.services.feed_slugs import dog_slug_from_name, generate_unique_feed_secret

    for dog in ClientProfile.objects.all().iterator():
        email = (dog.owner_email or '').strip().lower()
        if email and not CustomerOwner.objects.filter(owner_email__iexact=email).exists():
            CustomerOwner.objects.create(
                owner_email=email,
                owner_name=dog.owner_name or email,
                owner_phone=dog.owner_phone or '',
            )
        update_fields = []
        if not dog.feed_dog_slug:
            dog.feed_dog_slug = dog_slug_from_name(dog.dog_name)
            update_fields.append('feed_dog_slug')
        if not dog.feed_secret:
            dog.feed_secret = generate_unique_feed_secret()
            update_fields.append('feed_secret')
        if update_fields:
            update_fields.append('updated_at')
            dog.save(update_fields=update_fields)


class Migration(migrations.Migration):

    dependencies = [
        ('operations', '0017_structured_home_address'),
    ]

    operations = [
        migrations.RunPython(backfill_owners_and_feed, migrations.RunPython.noop),
    ]
