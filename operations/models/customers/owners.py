from typing import TYPE_CHECKING
from django.db import models
from django.utils import timezone

from operations.models.base import TenantAwareModel
from operations.services.addresses import (
    CANADIAN_PROVINCES,
    format_address,
    maps_search_url,
)

if TYPE_CHECKING:
    from .dogs import ClientProfile


class CustomerOwner(TenantAwareModel):
    """
    The owner's relationship with Dad4dogs — one record per owner email per workspace.
    Certificate of insurance applies here, not per dog.
    """
    owner_email = models.EmailField()
    owner_name = models.CharField(max_length=200)
    owner_salutation = models.CharField(
        max_length=40,
        blank=True,
        help_text='Pronouns or salutation for statements and waivers (e.g. Ms., they/them).',
    )
    owner_phone = models.CharField(
        max_length=30,
        blank=True,
        help_text='Primary mobile — required for real-time alerts.',
    )
    address_street = models.CharField(
        max_length=200,
        blank=True,
        help_text='Street number and name.',
    )
    address_unit = models.CharField(
        max_length=40,
        blank=True,
        help_text='Unit, apartment, or suite — optional.',
    )
    address_city = models.CharField(max_length=100, blank=True)
    address_province = models.CharField(
        max_length=2,
        blank=True,
        choices=CANADIAN_PROVINCES,
        help_text='Two-letter province or territory code.',
    )
    address_postal_code = models.CharField(
        max_length=7,
        blank=True,
        help_text='Canadian postal code (e.g. N6B 1G2).',
    )
    home_address = models.TextField(
        blank=True,
        help_text='Formatted or legacy free-text home address. Rebuilt from structured fields on save.',
    )
    emergency_contact_name = models.CharField(max_length=200, blank=True)
    emergency_contact_phone = models.CharField(max_length=30, blank=True)
    emergency_contact_relationship = models.CharField(
        max_length=120,
        blank=True,
        help_text='e.g. Neighbor with house key, Aunt across town.',
    )
    authorized_pickup_names = models.TextField(
        blank=True,
        help_text='One name per line — individuals allowed to take any dog home.',
    )
    coi_sent_at = models.DateTimeField(null=True, blank=True)
    coi_confirmed_received = models.BooleanField(default=False)
    coi_confirmed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['owner_name']
        verbose_name = 'customer (owner)'
        verbose_name_plural = 'customers (owners)'
        constraints = [
            models.UniqueConstraint(
                fields=['tenant', 'owner_email'],
                name='unique_tenant_customer_owner_email',
            ),
        ]

    def __str__(self):
        return f'{self.owner_name} ({self.owner_email})'

    @property
    def list_name(self) -> str:
        parts = (self.owner_name or '').strip().split()
        if len(parts) < 2:
            return (self.owner_name or '').strip()
        return f'{parts[-1]}, {" ".join(parts[:-1])}'

    @property
    def list_sort_key(self) -> tuple:
        parts = (self.owner_name or '').strip().split()
        if not parts:
            return ('', '')
        if len(parts) == 1:
            return (parts[0].lower(), '')
        return (parts[-1].lower(), ' '.join(parts[:-1]).lower())

    def build_home_address(self, *, oneline: bool = False) -> str:
        return format_address(
            street=self.address_street,
            unit=self.address_unit,
            city=self.address_city,
            province=self.address_province,
            postal=self.address_postal_code,
            oneline=oneline,
        )

    @property
    def formatted_address(self) -> str:
        structured = self.build_home_address()
        return structured or (self.home_address or '').strip()

    @property
    def address_oneline(self) -> str:
        structured = self.build_home_address(oneline=True)
        if structured:
            return structured
        blob = (self.home_address or '').strip()
        if not blob:
            return ''
        return ', '.join(line.strip() for line in blob.splitlines() if line.strip())

    @property
    def address_maps_url(self) -> str:
        return maps_search_url(self.address_oneline)

    def save(self, *args, **kwargs):
        formatted = self.build_home_address()
        if formatted:
            self.home_address = formatted
            update_fields = kwargs.get('update_fields')
            if update_fields is not None and 'home_address' not in update_fields:
                kwargs = {**kwargs, 'update_fields': [*update_fields, 'home_address']}
        super().save(*args, **kwargs)

    @property
    def authorized_pickup_list(self) -> list[str]:
        return [
            line.strip()
            for line in self.authorized_pickup_names.splitlines()
            if line.strip()
        ]

    @property
    def coi_status(self) -> str:
        if self.coi_confirmed_received:
            return 'received'
        if self.coi_sent_at:
            return 'sent'
        return 'not_sent'

    def mark_coi_sent(self):
        self.coi_sent_at = timezone.now()
        self.save(update_fields=['coi_sent_at', 'updated_at'])

    def mark_coi_received(self):
        self.coi_confirmed_received = True
        self.coi_confirmed_at = timezone.now()
        if not self.coi_sent_at:
            self.coi_sent_at = self.coi_confirmed_at
        self.save(update_fields=[
            'coi_confirmed_received', 'coi_confirmed_at', 'coi_sent_at', 'updated_at',
        ])

    @classmethod
    def for_client(cls, client: 'ClientProfile') -> 'CustomerOwner | None':
        email = (client.owner_email or '').strip()
        if not email:
            return None
        qs = cls.objects.filter(owner_email__iexact=email)
        if getattr(client, 'tenant_id', None):
            qs = qs.filter(tenant_id=client.tenant_id)
        return qs.first()

    @classmethod
    def ensure_for_client(cls, client: 'ClientProfile') -> 'CustomerOwner':
        from operations.services.context_tenant import get_active_workspace

        tenant = client.tenant if getattr(client, 'tenant_id', None) else get_active_workspace()
        owner, _ = cls.objects.get_or_create(
            tenant=tenant,
            owner_email=client.owner_email.lower().strip(),
            defaults={
                'owner_name': client.owner_name,
                'owner_phone': client.owner_phone,
            },
        )
        return owner