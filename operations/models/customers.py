from django.db import models
from django.urls import reverse
from django.utils import timezone

from operations.services.feed_slugs import dog_slug_from_name, generate_unique_feed_secret


class CustomerOwner(models.Model):
    """
    The owner's relationship with Dad4dogs — one record per owner email.
    Certificate of insurance applies here, not per dog.
    """
    owner_email = models.EmailField(unique=True)
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
    home_address = models.TextField(
        blank=True,
        help_text='Physical home address for records, insurance, and emergency drop-off.',
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

    def __str__(self):
        return f'{self.owner_name} ({self.owner_email})'

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
    def ensure_for_client(cls, client: 'ClientProfile') -> 'CustomerOwner':
        owner, _ = cls.objects.get_or_create(
            owner_email=client.owner_email.lower().strip(),
            defaults={
                'owner_name': client.owner_name,
                'owner_phone': client.owner_phone,
            },
        )
        return owner


class ClientProfile(models.Model):
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

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['owner_email', 'dog_name'],
                name='unique_owner_email_dog_name',
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

    def advance_pipeline(self):
        order = [
            self.PipelineStage.INQUIRY,
            self.PipelineStage.MEET_GREET,
            self.PipelineStage.EVALUATION,
            self.PipelineStage.APPROVED,
        ]
        idx = order.index(self.pipeline_stage)
        if idx < len(order) - 1:
            self.pipeline_stage = order[idx + 1]
            if self.pipeline_stage == self.PipelineStage.APPROVED:
                self.approved_at = timezone.now()
            self.save()

    def ensure_feed_credentials(self, *, save: bool = True) -> 'ClientProfile':
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
        slug = dog_slug_from_name(self.dog_name)
        if self.feed_dog_slug != slug:
            self.feed_dog_slug = slug
            if save:
                self.save(update_fields=['feed_dog_slug', 'updated_at'])

    def regenerate_feed_secret(self, *, save: bool = True) -> str:
        """Issue a new secret — old feed links stop working."""
        self.feed_secret = generate_unique_feed_secret()
        if not self.feed_dog_slug:
            self.feed_dog_slug = dog_slug_from_name(self.dog_name)
        if save:
            self.save(update_fields=['feed_secret', 'feed_dog_slug', 'updated_at'])
        return self.feed_secret

    def feed_url_path(self) -> str:
        self.ensure_feed_credentials()
        return reverse(
            'operations:customer_feed',
            kwargs={
                'feed_secret': self.feed_secret,
                'feed_dog_slug': self.feed_dog_slug,
            },
        )

    def feed_url(self, *, request=None) -> str:
        path = self.feed_url_path()
        if request is not None:
            return request.build_absolute_uri(path)
        from django.conf import settings

        base = getattr(settings, 'PUBLIC_SITE_URL', '').rstrip('/')
        if base:
            return f'{base}{path}'
        return path


class FeedAccessLog(models.Model):
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


class VaccinationRecord(models.Model):
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

    def mark_validated(self):
        self.validated = True
        self.validated_at = timezone.now()
        self.save(update_fields=['validated', 'validated_at'])