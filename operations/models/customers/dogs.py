from datetime import timedelta
from django.db import models
from django.db.models import Count, Max, Q
from django.urls import reverse
from django.utils import timezone

from operations.models.base import TenantAwareModel
from .constants import (
    VAX_EXPIRY_WARNING_DAYS,
    VAX_STATUS_EXPIRED,
    VAX_STATUS_EXPIRING,
    VAX_STATUS_MISSING,
    VAX_STATUS_OK,
)
from .owners import CustomerOwner


class ClientProfileQuerySet(models.QuerySet):
    def visible(self):
        return self.filter(is_hidden=False)

    def hidden(self):
        return self.filter(is_hidden=True)

    def with_vaccination_expiry(self):
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

    def evaluation_stay_blockers(self) -> list[str]:
        """Block Initial Evaluation booking until M&G Passed + paperwork ready."""
        from operations.services.pipeline import dog_has_passed_meet_greet

        blockers = []
        if self.is_hidden:
            blockers.append(
                f'{self.dog_name} is hidden from the client list and cannot be booked.'
            )
        if self.pipeline_stage != self.PipelineStage.EVALUATION:
            blockers.append(
                f'{self.dog_name} must be in Evaluation (Pass Meet & Greet first). '
                f'Currently {self.get_pipeline_stage_display()}.'
            )
        if not dog_has_passed_meet_greet(self):
            blockers.append(
                f'Pass a completed Meet & Greet for {self.dog_name} before Initial Evaluation.'
            )
        if not self.has_current_vaccination:
            blockers.append(
                f'{self.dog_name} needs a current validated vaccination before Evaluation.'
            )
        owner = self.customer_owner
        if not owner.coi_confirmed_received:
            blockers.append(
                f'Confirm COI for {owner.owner_name} before Initial Evaluation.'
            )
        return blockers

    def can_schedule_meet_greet(self) -> bool:
        return (
            not self.is_hidden
            and self.pipeline_stage in (
                self.PipelineStage.INQUIRY,
                self.PipelineStage.MEET_GREET,
            )
        )

    def advance_pipeline(self) -> bool:
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
        # Leaf import adhering to PHILOSOPHY.md §5
        from operations.services.feed_interactions.slugs import (
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
        from operations.services.feed_interactions.slugs import dog_slug_from_name

        slug = dog_slug_from_name(self.dog_name)
        if self.feed_dog_slug != slug:
            self.feed_dog_slug = slug
            if save:
                self.save(update_fields=['feed_dog_slug', 'updated_at'])

    def regenerate_feed_secret(self, *, save: bool = True) -> str:
        from operations.services.feed_interactions.slugs import (
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
        return f'{base}{path}' if base else path