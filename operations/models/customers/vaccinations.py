from datetime import timedelta
from django.db import models
from django.utils import timezone

from operations.models.base import TenantAwareModel
from .constants import VAX_EXPIRY_WARNING_DAYS
from .dogs import ClientProfile


class VaccinationRecord(TenantAwareModel):
    client = models.ForeignKey(
        ClientProfile,
        on_delete=models.CASCADE,
        related_name='vaccination_records',
    )
    papers_received = models.BooleanField(default=True)
    received_at = models.DateField(
        default=timezone.localdate,
        help_text='Date vaccination papers were received.',
    )
    expires_at = models.DateField(
        help_text='Date vaccinations expire per veterinarian papers.',
    )
    validated = models.BooleanField(default=False)
    validated_at = models.DateTimeField(null=True, blank=True)
    vet_clinic = models.CharField(max_length=200, blank=True)
    vaccination_details = models.TextField(
        blank=True,
        help_text='Rabies, kennel cough, expiry dates, etc.',
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-received_at', '-created_at']

    def __str__(self):
        return f'{self.client.dog_name} — expires {self.expires_at}'

    @property
    def is_expired(self) -> bool:
        return self.expires_at < timezone.localdate()

    @property
    def is_expiring_soon(self) -> bool:
        if not self.validated or self.is_expired:
            return False
        today = timezone.localdate()
        return self.expires_at <= today + timedelta(days=VAX_EXPIRY_WARNING_DAYS)

    def mark_validated(self):
        self.validated = True
        self.validated_at = timezone.now()
        self.save(update_fields=['validated', 'validated_at'])