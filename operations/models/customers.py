from django.db import models
from django.utils import timezone


class CustomerOwner(models.Model):
    """
    The owner's relationship with Dad4dogs — one record per owner email.
    Certificate of insurance applies here, not per dog.
    """
    owner_email = models.EmailField(unique=True)
    owner_name = models.CharField(max_length=200)
    owner_phone = models.CharField(max_length=30, blank=True)
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
    notes = models.TextField(blank=True)
    pipeline_stage = models.CharField(
        max_length=20,
        choices=PipelineStage.choices,
        default=PipelineStage.INQUIRY,
    )
    approved_at = models.DateTimeField(null=True, blank=True)
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