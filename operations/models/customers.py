from datetime import timedelta

from django.db import models
from django.db.models import Count, Max, Q
from django.urls import reverse
from django.utils import timezone

from operations.models.base import TenantAwareModel
from operations.services.addresses import (
    CANADIAN_PROVINCES,
    format_address,
    maps_search_url,
)

VAX_EXPIRY_WARNING_DAYS = 30

VAX_STATUS_OK = 'ok'
VAX_STATUS_EXPIRING = 'expiring'
VAX_STATUS_EXPIRED = 'expired'
VAX_STATUS_MISSING = 'missing'

VAX_FILTER_CHOICES = (
    (VAX_STATUS_EXPIRING, 'Expiring (30 days)'),
    (VAX_STATUS_EXPIRED, 'Expired'),
    (VAX_STATUS_MISSING, 'No validated record'),
    (VAX_STATUS_OK, 'Current (30+ days)'),
)


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
        """Last, First for scannable client lists."""
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
        if structured:
            return structured
        return (self.home_address or '').strip()

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
        """Lookup only — never creates a row."""
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


class ClientProfileQuerySet(models.QuerySet):
    def visible(self):
        return self.filter(is_hidden=False)

    def hidden(self):
        return self.filter(is_hidden=True)

    def with_vaccination_expiry(self):
        """Annotate `current_vax_expires` = latest validated `expires_at` (or NULL)."""
        if 'current_vax_expires' in self.query.annotations:
            return self
        return self.annotate(
            current_vax_expires=Max(
                'vaccination_records__expires_at',
                filter=Q(vaccination_records__validated=True),
            ),
        )

    def filter_vaccination_status(self, status, *, today=None):
        today = today or timezone.localdate()
        warning_end = today + timedelta(days=VAX_EXPIRY_WARNING_DAYS)
        qs = self.with_vaccination_expiry()
        if status == VAX_STATUS_EXPIRING:
            return qs.filter(
                current_vax_expires__gte=today,
                current_vax_expires__lte=warning_end,
            )
        if status == VAX_STATUS_EXPIRED:
            return qs.filter(current_vax_expires__lt=today)
        if status == VAX_STATUS_MISSING:
            return qs.filter(current_vax_expires__isnull=True)
        if status == VAX_STATUS_OK:
            return qs.filter(current_vax_expires__gt=warning_end)
        return qs

    def vaccination_status_counts(self, *, today=None):
        today = today or timezone.localdate()
        warning_end = today + timedelta(days=VAX_EXPIRY_WARNING_DAYS)
        return self.with_vaccination_expiry().aggregate(
            expiring=Count(
                'pk',
                filter=Q(
                    current_vax_expires__gte=today,
                    current_vax_expires__lte=warning_end,
                ),
            ),
            expired=Count('pk', filter=Q(current_vax_expires__lt=today)),
            missing=Count('pk', filter=Q(current_vax_expires__isnull=True)),
            ok=Count('pk', filter=Q(current_vax_expires__gt=warning_end)),
        )


class ClientProfile(TenantAwareModel):
    class PipelineStage(models.TextChoices):
        INQUIRY = 'inquiry', 'Inquiry'
        MEET_GREET = 'meet_greet', 'Meet & Greet'
        EVALUATION = 'evaluation', 'Evaluation'
        APPROVED = 'approved', 'Approved Repeat Client'

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
        choices=PipelineStage.choices,
        default=PipelineStage.INQUIRY,
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
        """True when dog name looks like the owner's first name or is still TBD."""
        if not self.dog_name or self.dog_name.upper() == 'TBD':
            return True
        owner_first = self.owner_name.split()[0].lower() if self.owner_name else ''
        return bool(owner_first) and self.dog_name.lower() == owner_first

    @property
    def has_validated_vaccination(self) -> bool:
        return self.has_current_vaccination

    @property
    def has_current_vaccination(self) -> bool:
        today = timezone.localdate()
        return self.vaccination_records.filter(
            validated=True,
            expires_at__gte=today,
        ).exists()

    @property
    def current_vaccination_expires_at(self):
        """Latest validated expiry. Uses `current_vax_expires` when annotated."""
        if hasattr(self, 'current_vax_expires'):
            return self.current_vax_expires
        rec = (
            self.vaccination_records.filter(validated=True)
            .order_by('-expires_at')
            .only('expires_at')
            .first()
        )
        return rec.expires_at if rec else None

    @property
    def vaccination_status(self) -> str:
        """ok | expiring | expired | missing — latest validated record vs today."""
        cached = getattr(self, '_vaccination_status', None)
        if cached is not None:
            return cached
        today = timezone.localdate()
        expires = self.current_vaccination_expires_at
        if expires is None:
            status = VAX_STATUS_MISSING
        elif expires < today:
            status = VAX_STATUS_EXPIRED
        elif expires <= today + timedelta(days=VAX_EXPIRY_WARNING_DAYS):
            status = VAX_STATUS_EXPIRING
        else:
            status = VAX_STATUS_OK
        self._vaccination_status = status
        return status

    def hide(self):
        if not self.is_hidden:
            self.is_hidden = True
            self.save(update_fields=['is_hidden', 'updated_at'])

    def unhide(self):
        if self.is_hidden:
            self.is_hidden = False
            self.save(update_fields=['is_hidden', 'updated_at'])

    def standard_stay_blockers(self) -> list[str]:
        """Reasons this dog cannot be booked for a standard stay (VisitForm create)."""
        blockers = []
        if self.is_hidden:
            blockers.append(
                f'{self.dog_name} is hidden from the client list and cannot be booked for a new stay.'
            )
        if self.pipeline_stage != self.PipelineStage.APPROVED:
            blockers.append(
                f'{self.dog_name} is still in {self.get_pipeline_stage_display()}. '
                f'Standard stays require Approved.'
            )
        if not self.has_current_vaccination:
            blockers.append(
                f'{self.dog_name} has no current validated vaccination.'
            )
        owner = self.customer_owner
        if not owner.coi_confirmed_received:
            blockers.append(
                f'COI has not been confirmed for {owner.owner_name}.'
            )
        return blockers

    def advance_pipeline(self) -> bool:
        """Move one stage forward. Returns True if the stage changed."""
        order = [
            self.PipelineStage.INQUIRY,
            self.PipelineStage.MEET_GREET,
            self.PipelineStage.EVALUATION,
            self.PipelineStage.APPROVED,
        ]
        try:
            idx = order.index(self.pipeline_stage)
        except ValueError:
            return False
        if idx >= len(order) - 1:
            return False
        self.pipeline_stage = order[idx + 1]
        if self.pipeline_stage == self.PipelineStage.APPROVED:
            self.approved_at = timezone.now()
        self.save()
        return True

    def ensure_feed_credentials(self, *, save: bool = True) -> 'ClientProfile':
        from operations.services.feed_interactions import (
            dog_slug_from_name,
            generate_unique_feed_secret,
        )

        update_fields = []
        if not self.feed_dog_slug:
            self.feed_dog_slug = dog_slug_from_name(self.dog_name)
            update_fields.append('feed_dog_slug')
        if not self.feed_secret:
            self.feed_secret = generate_unique_feed_secret()
            update_fields.append('feed_secret')
        if update_fields and save:
            update_fields.append('updated_at')
            self.save(update_fields=update_fields)
        return self

    def sync_feed_dog_slug(self, *, save: bool = True) -> None:
        """Keep the dog slug aligned with the current dog name."""
        from operations.services.feed_interactions import dog_slug_from_name

        slug = dog_slug_from_name(self.dog_name)
        if self.feed_dog_slug != slug:
            self.feed_dog_slug = slug
            if save:
                self.save(update_fields=['feed_dog_slug', 'updated_at'])

    def regenerate_feed_secret(self, *, save: bool = True) -> str:
        """Issue a new secret — old feed links stop working."""
        from operations.services.feed_interactions import (
            dog_slug_from_name,
            generate_unique_feed_secret,
        )

        self.feed_secret = generate_unique_feed_secret()
        if not self.feed_dog_slug:
            self.feed_dog_slug = dog_slug_from_name(self.dog_name)
        if save:
            self.save(update_fields=['feed_secret', 'feed_dog_slug', 'updated_at'])
        return self.feed_secret

    def feed_url_path(self, *, create: bool = True) -> str:
        if create:
            self.ensure_feed_credentials()
        if not self.feed_secret or not self.feed_dog_slug:
            return ''
        return reverse(
            'operations:customer_feed',
            kwargs={
                'feed_secret': self.feed_secret,
                'feed_dog_slug': self.feed_dog_slug,
            },
        )

    def feed_url(self, *, request=None, create: bool = True) -> str:
        path = self.feed_url_path(create=create)
        if not path:
            return ''
        if request is not None:
            return request.build_absolute_uri(path)
        from django.conf import settings

        base = getattr(settings, 'PUBLIC_SITE_URL', '').rstrip('/')
        if base:
            return f'{base}{path}'
        return path


class FeedAccessLog(TenantAwareModel):
    """Anonymous per-browser access log for customer feeds (local visitor ID cookie)."""
    client = models.ForeignKey(
        ClientProfile,
        on_delete=models.CASCADE,
        related_name='feed_access_logs',
    )
    visitor_id = models.CharField(max_length=36)
    user_agent = models.CharField(max_length=500, blank=True)
    accessed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-accessed_at']
        indexes = [
            models.Index(fields=['client', 'accessed_at']),
            models.Index(fields=['client', 'visitor_id']),
        ]

    def __str__(self):
        return f'{self.client.dog_name} — {self.visitor_id[:8]}… @ {self.accessed_at:%Y-%m-%d %H:%M}'


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
        """Validated coverage that ends within the 30-day warning window."""
        if not self.validated or self.is_expired:
            return False
        today = timezone.localdate()
        return self.expires_at <= today + timedelta(days=VAX_EXPIRY_WARNING_DAYS)

    def mark_validated(self):
        self.validated = True
        self.validated_at = timezone.now()
        self.save(update_fields=['validated', 'validated_at'])