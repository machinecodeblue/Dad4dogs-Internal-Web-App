from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

DEFAULT_STANDARD_CAPACITY = 8
DEFAULT_INSURANCE_CEILING = 10


class BusinessProfile(models.Model):
    """
    Singleton record for Dad4dogs baseline business details.
    Use BusinessProfile.load() — never create multiple rows.
    """
    singleton_key = models.CharField(max_length=1, default='X', unique=True, editable=False)

    business_name = models.CharField(
        max_length=200,
        default='Dad4dogs',
        help_text='Display name on calendar invites (ORGANIZER CN=).',
    )
    business_email = models.EmailField(
        blank=True,
        help_text='Organizer email on calendar invites — should match your Gmail send-as address.',
    )

    address = models.TextField(
        blank=True,
        help_text='Service address; used as LOCATION on calendar invites.',
    )
    hours_of_operation = models.TextField(
        blank=True,
        help_text='When clients can reach you or drop off/pick up.',
    )

    main_phone = models.CharField(max_length=30, blank=True)
    secondary_phone = models.CharField(
        max_length=30,
        blank=True,
        help_text='Alternate line (e.g. secondary mobile).',
    )
    emergency_phone = models.CharField(
        max_length=30,
        blank=True,
        help_text='Number clients should call if there is an urgent problem.',
    )

    standard_capacity = models.PositiveSmallIntegerField(
        default=DEFAULT_STANDARD_CAPACITY,
        validators=[MinValueValidator(1), MaxValueValidator(50)],
        help_text='Comfortable daily dog count. Days above this show a warning.',
    )
    insurance_ceiling = models.PositiveSmallIntegerField(
        default=DEFAULT_INSURANCE_CEILING,
        validators=[MinValueValidator(1), MaxValueValidator(50)],
        help_text='Hard maximum for new bookings (insurance). Cannot schedule above this.',
    )

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'business profile'
        verbose_name_plural = 'business profile'

    def __str__(self):
        return self.business_name or 'Dad4dogs'

    def clean(self):
        super().clean()
        if (
            self.standard_capacity
            and self.insurance_ceiling
            and self.insurance_ceiling < self.standard_capacity
        ):
            raise ValidationError({
                'insurance_ceiling': 'Insurance maximum must be at least the standard daily capacity.',
            })

    def save(self, *args, **kwargs):
        self.singleton_key = 'X'
        super().save(*args, **kwargs)

    @classmethod
    def load(cls) -> 'BusinessProfile':
        profile, _ = cls.objects.get_or_create(singleton_key='X')
        return profile

    @property
    def formatted_address(self) -> str:
        return self.address.strip()

    @property
    def formatted_hours(self) -> str:
        return self.hours_of_operation.strip()

    @property
    def calendar_organizer_email(self) -> str:
        return self.business_email.strip()

    @property
    def calendar_organizer_name(self) -> str:
        return (self.business_name or 'Dad4dogs').strip()

    @property
    def calendar_location(self) -> str:
        return self.formatted_address