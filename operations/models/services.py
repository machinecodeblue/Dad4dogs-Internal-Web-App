from decimal import Decimal

from django.db import models

from operations.models.base import TenantAwareModel


class BusinessService(TenantAwareModel):
    """
    Commercial offering in the operator's catalog (per workspace).

    Phase 1: CRUD under /settings/services/. Checkout still uses operations/pricing.py.
    """

    class TargetCategory(models.TextChoices):
        DOG = 'DOG', 'Dog'
        CAT = 'CAT', 'Cat'
        SMALL_PET = 'SMALL_PET', 'Small pet'
        PROPERTY_ONLY = 'PROPERTY_ONLY', 'Property only'

    class RateType(models.TextChoices):
        FLAT = 'FLAT', 'Flat'
        HOURLY = 'HOURLY', 'Hourly'
        DAILY = 'DAILY', 'Daily'

    name = models.CharField(max_length=150)
    slug = models.SlugField(max_length=100)
    summary = models.CharField(
        max_length=240,
        blank=True,
        help_text='Optional short blurb for lists and future booking pickers (customer-facing).',
    )
    description = models.TextField(
        help_text=(
            'Full customer-facing service plan: what is included, expectations, and boundaries. '
            'Plain text only.'
        ),
    )
    staff_notes = models.TextField(
        blank=True,
        help_text='Internal notes only — never show on customer emails, statements, or public pages.',
    )
    target_category = models.CharField(
        max_length=20,
        choices=TargetCategory.choices,
        default=TargetCategory.DOG,
    )
    rate_type = models.CharField(
        max_length=20,
        choices=RateType.choices,
        default=RateType.FLAT,
    )
    base_rate = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal('0.00'))
    is_active = models.BooleanField(
        default=True,
        help_text='Inactive services are hidden from booking dropdowns (soft-hide).',
    )
    capacity_exempt = models.BooleanField(
        default=False,
        help_text='If True, future bookings skip facility capacity checks (Phase 2 wiring).',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['target_category', 'name']
        constraints = [
            models.UniqueConstraint(
                fields=['tenant', 'slug'],
                name='unique_tenant_business_service_slug',
            ),
        ]

    def __str__(self):
        return self.name


class ServiceBehaviorRule(TenantAwareModel):
    """Optional rate modifier for a BusinessService (duration / time-window triggers)."""

    class TriggerType(models.TextChoices):
        DURATION_UNDER = 'DURATION_UNDER', 'Duration under (hours)'
        DURATION_OVER = 'DURATION_OVER', 'Duration over (hours)'
        TIME_WINDOW = 'TIME_WINDOW', 'Time window'

    service = models.ForeignKey(
        BusinessService,
        on_delete=models.CASCADE,
        related_name='behavior_rules',
    )
    trigger_type = models.CharField(max_length=20, choices=TriggerType.choices)
    threshold_value = models.PositiveIntegerField(
        help_text='Hours or time-window parameter depending on trigger_type.',
    )
    modified_rate = models.DecimalField(max_digits=8, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['trigger_type', 'threshold_value']

    def __str__(self):
        return f'{self.service.slug}: {self.trigger_type} {self.threshold_value}'

    def save(self, *args, **kwargs):
        if not self.tenant_id and self.service_id:
            self.tenant_id = self.service.tenant_id
        super().save(*args, **kwargs)
