from django.db import models

from operations.models.base import TenantAwareModel
from operations.models.customers.owners import CustomerOwner

from .feed import DogFeedMixin
from .pipeline import DogPipelineMixin
from .querysets import ClientProfileQuerySet
from .vaccinations import DogVaccinationMixin


class ClientProfile(
    TenantAwareModel,
    DogPipelineMixin,
    DogVaccinationMixin,
    DogFeedMixin,
):
    owner_name = models.CharField(max_length=200)
    owner_email = models.EmailField()
    owner_phone = models.CharField(max_length=30, blank=True)
    dog_name = models.CharField(max_length=100)
    vet_clinic_name = models.CharField(max_length=200, blank=True)
    vet_name = models.CharField(max_length=200, blank=True)
    vet_clinic_phone = models.CharField(max_length=30, blank=True)
    emergency_vet_clinic = models.CharField(
        max_length=200,
        blank=True,
        help_text='Preferred 24-hour emergency hospital when regular clinic is closed.',
    )
    emergency_vet_phone = models.CharField(max_length=30, blank=True)
    vet_care_authorization = models.TextField(
        blank=True,
        help_text='Dollar cap or directive for lifesaving triage before owner contact.',
    )
    notes = models.TextField(blank=True)
    is_hidden = models.BooleanField(
        default=False,
        help_text='Hidden dogs stay on file with visits and photos, but leave the client list.',
    )
    pipeline_stage = models.CharField(
        max_length=20,
        choices=DogPipelineMixin.PipelineStage.choices,
        default=DogPipelineMixin.PipelineStage.INQUIRY,
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    feed_secret = models.CharField(
        max_length=40,
        unique=True,
        null=True,
        blank=True,
        help_text='Speakable secret for customer feed URL (e.g. squeakytiki).',
    )
    feed_dog_slug = models.CharField(
        max_length=80,
        blank=True,
        help_text='URL segment from dog name (e.g. lulu).',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = ClientProfileQuerySet.as_manager()

    class Meta:
        app_label = 'operations'
        constraints = [
            models.UniqueConstraint(
                fields=['tenant', 'owner_email', 'dog_name'],
                name='unique_tenant_owner_email_dog_name',
            ),
        ]
        ordering = ['dog_name', 'owner_name']

    def __str__(self):
        return f'{self.dog_name} ({self.owner_name})'

    @property
    def customer_owner(self) -> CustomerOwner:
        return CustomerOwner.ensure_for_client(self)

    @property
    def needs_dog_name(self) -> bool:
        if not self.dog_name or self.dog_name.upper() == 'TBD':
            return True
        owner_first = self.owner_name.split()[0].lower() if self.owner_name else ''
        return bool(owner_first) and self.dog_name.lower() == owner_first

    def hide(self):
        if not self.is_hidden:
            self.is_hidden = True
            self.save(update_fields=['is_hidden', 'updated_at'])

    def unhide(self):
        if self.is_hidden:
            self.is_hidden = False
            self.save(update_fields=['is_hidden', 'updated_at'])
