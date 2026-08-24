from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('operations', '0019_clientprofile_is_hidden'),
    ]

    operations = [
        migrations.AddField(
            model_name='businessprofile',
            name='standard_capacity',
            field=models.PositiveSmallIntegerField(
                default=8,
                help_text='Comfortable daily dog count. Days above this show a warning.',
                validators=[MinValueValidator(1), MaxValueValidator(50)],
            ),
        ),
        migrations.AddField(
            model_name='businessprofile',
            name='insurance_ceiling',
            field=models.PositiveSmallIntegerField(
                default=10,
                help_text='Hard maximum for new bookings (insurance). Cannot schedule above this.',
                validators=[MinValueValidator(1), MaxValueValidator(50)],
            ),
        ),
    ]
