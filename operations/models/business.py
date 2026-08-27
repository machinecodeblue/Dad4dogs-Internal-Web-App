from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

DEFAULT_STANDARD_CAPACITY = 8
DEFAULT_INSURANCE_CEILING = 10


class BusinessProfile(models.Model):
    """
    Per-workspace brand / contact baseline (OneToOne to Workspace).

    Capacity integers live on CapacitySettings — not here.
    Use BusinessProfile.load() for the active single-operator workspace.
    """

    workspace = models.OneToOneField(
        'operations.Workspace',
        on_delete=models.CASCADE,
        related_name='profile',
        null=True,
        blank=True,
    )

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

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'business profile'
        verbose_name_plural = 'business profile'

    def __str__(self):
        return self.business_name or 'Dad4dogs'

    @classmethod
    def load(cls) -> 'BusinessProfile':
        from operations.services.context_tenant import get_active_workspace

        workspace = get_active_workspace()
        profile, _ = cls.objects.get_or_create(
            workspace=workspace,
            defaults={'business_name': 'Dad4dogs'},
        )
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


class CapacitySettings(models.Model):
    """
    Per-workspace facility capacity numbers.

    Warn vs block orchestration lives in operations/capacity.py — not on this model.
    Phase 1: standard_capacity + insurance_ceiling only.
    """

    workspace = models.OneToOneField(
        'operations.Workspace',
        on_delete=models.CASCADE,
        related_name='capacity_settings',
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
        verbose_name = 'capacity settings'
        verbose_name_plural = 'capacity settings'

    def __str__(self):
        return (
            f'{self.workspace.slug}: '
            f'{self.standard_capacity}/{self.insurance_ceiling}'
        )

    def clean(self):
        super().clean()
        if (
            self.standard_capacity
            and self.insurance_ceiling
            and self.insurance_ceiling < self.standard_capacity
        ):
            raise ValidationError({
                'insurance_ceiling': (
                    'Insurance maximum must be at least the standard daily capacity.'
                ),
            })

    @classmethod
    def load(cls) -> 'CapacitySettings':
        from operations.services.context_tenant import get_active_workspace

        workspace = get_active_workspace()
        settings, _ = cls.objects.get_or_create(workspace=workspace)
        return settings
