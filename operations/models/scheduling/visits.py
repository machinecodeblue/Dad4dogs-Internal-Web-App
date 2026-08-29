from datetime import datetime
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from operations.capacity import check_visit_capacity, overlapping_dog_visit
from operations.models.base import TenantAwareModel
from operations.models.customers import ClientProfile
from operations.pricing import calculate_fee
from .series import VisitSeries


class Visit(TenantAwareModel):
    class Status(models.TextChoices):
        SCHEDULED = 'scheduled', 'Scheduled'
        CHECKED_IN = 'checked_in', 'Checked In'
        COMPLETED = 'completed', 'Completed'
        CANCELLED = 'cancelled', 'Cancelled'

    class EvaluationOutcome(models.TextChoices):
        APPROVE = 'approve', 'Approve'
        REJECT = 'reject', 'Reject'
        FURTHER = 'further', 'Recommend further evaluation'

    class MeetGreetOutcome(models.TextChoices):
        PASS = 'pass', 'Pass'
        DECLINE = 'decline', 'Decline'

    client = models.ForeignKey(ClientProfile, on_delete=models.CASCADE, related_name='visits')
    business_service = models.ForeignKey(
        'operations.BusinessService',
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name='visits',
        help_text='Catalog offering for this stay. Required on new bookings; null on legacy visits.',
    )
    series = models.ForeignKey(
        VisitSeries,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='visits',
    )
    series_position = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text='1-based index within the repeat series.',
    )
    scheduled_start = models.DateTimeField()
    scheduled_end = models.DateTimeField()
    actual_arrival = models.DateTimeField(null=True, blank=True)
    actual_departure = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.SCHEDULED)
    calculated_fee = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    fee_breakdown = models.JSONField(default=list, blank=True)
    notes = models.TextField(blank=True)
    evaluation_outcome = models.CharField(
        max_length=20,
        choices=EvaluationOutcome.choices,
        blank=True,
        help_text='Set after Initial Evaluation check-out (approve / reject / further).',
    )
    evaluation_notes = models.TextField(
        blank=True,
        help_text='How the dog did and outcome rationale for Initial Evaluation.',
    )
    meet_greet_outcome = models.CharField(
        max_length=20,
        choices=MeetGreetOutcome.choices,
        blank=True,
        help_text='Set after Meet & Greet check-out (pass / decline).',
    )
    meet_greet_notes = models.TextField(
        blank=True,
        help_text='Notes from the Meet & Greet (suitability / decline reason).',
    )
    confirmation_email_sent_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text='When the customer was emailed this booking confirmation.',
    )
    cloned_from = models.ForeignKey(
        'self', null=True, blank=True, on_delete=models.SET_NULL, related_name='clones',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-scheduled_start']
        indexes = [
            models.Index(fields=['tenant', 'scheduled_start'], name='visit_tenant_start_idx'),
            models.Index(fields=['tenant', 'scheduled_end'], name='visit_tenant_end_idx'),
            models.Index(fields=['tenant', 'status'], name='visit_tenant_status_idx'),
        ]

    def __str__(self):
        return f'{self.client.dog_name} — {self.scheduled_start:%Y-%m-%d %H:%M}'

    def clean(self):
        if self.scheduled_end <= self.scheduled_start:
            raise ValidationError('Scheduled end must be after scheduled start.')

        client_id = self.client_id or getattr(self.client, 'pk', None)
        clash = overlapping_dog_visit(
            client_id,
            self.scheduled_start,
            self.scheduled_end,
            exclude_visit_id=self.pk,
        )
        if clash:
            raise ValidationError(
                f'{clash.client.dog_name} is already booked {clash.schedule_display}.'
            )

        if getattr(self, '_skip_capacity_check', False):
            return

        capacity = check_visit_capacity(self)
        if capacity['status'] == 'blocked':
            raise ValidationError(capacity['message'])

    _SCHEDULE_FIELDS = frozenset({'scheduled_start', 'scheduled_end', 'client', 'client_id'})

    def save(self, *args, **kwargs):
        skip_capacity = kwargs.pop('skip_capacity', False)
        previous = getattr(self, '_skip_capacity_check', False)
        self._skip_capacity_check = skip_capacity
        try:
            update_fields = kwargs.get('update_fields')
            if update_fields is None or self._SCHEDULE_FIELDS.intersection(update_fields):
                self.full_clean()
            super().save(*args, **kwargs)
        finally:
            self._skip_capacity_check = previous

    def _price_stay(self, arrival, departure):
        if self.business_service_id:
            from operations.services.pricing_engine import calculate_service_fee

            return calculate_service_fee(self.business_service, arrival, departure)
        return calculate_fee(arrival, departure)

    def check_in(self):
        if self.status != self.Status.SCHEDULED:
            raise ValidationError('Only scheduled visits can be checked in.')
        self.actual_arrival = timezone.now()
        self.status = self.Status.CHECKED_IN
        self.save(update_fields=['actual_arrival', 'status', 'updated_at'])

    def check_out(self):
        if self.pk:
            self.refresh_from_db()
        if self.status == self.Status.COMPLETED or self.calculated_fee is not None:
            raise ValidationError('This visit has already been checked out.')
        if self.status != self.Status.CHECKED_IN:
            raise ValidationError('Only checked-in visits can be checked out.')
        self.actual_departure = timezone.now()
        arrival = self.actual_arrival or self.scheduled_start
        fee, breakdown = self._price_stay(arrival, self.actual_departure)
        self.calculated_fee = fee
        self.fee_breakdown = breakdown
        self.status = self.Status.COMPLETED
        self.save(update_fields=[
            'actual_departure', 'calculated_fee', 'fee_breakdown', 'status', 'updated_at',
        ])

    def update_actual_times(self, *, arrival=None, departure=None):
        if self.status == self.Status.CHECKED_IN:
            if arrival is None:
                raise ValidationError('Enter the actual arrival time.')
            if departure is not None:
                raise ValidationError('Check out before setting a departure time.')
            self.actual_arrival = arrival
            self.save(update_fields=['actual_arrival', 'updated_at'])
            return

        if self.status == self.Status.COMPLETED:
            new_arrival = arrival if arrival is not None else self.actual_arrival
            new_departure = departure if departure is not None else self.actual_departure
            if new_arrival is None:
                raise ValidationError('Enter the actual arrival time.')
            if new_departure is None:
                raise ValidationError('Enter the actual departure time.')
            if new_departure <= new_arrival:
                raise ValidationError('Departure must be after arrival.')
            self.actual_arrival = new_arrival
            self.actual_departure = new_departure
            fee, breakdown = self._price_stay(new_arrival, new_departure)
            self.calculated_fee = fee
            self.fee_breakdown = breakdown
            self.save(update_fields=[
                'actual_arrival',
                'actual_departure',
                'calculated_fee',
                'fee_breakdown',
                'updated_at',
            ])
            return

        raise ValidationError('Only checked-in or completed visits can have times corrected.')

    def clone_to_date(self, new_date):
        start = timezone.localtime(self.scheduled_start)
        duration = self.scheduled_end - self.scheduled_start
        new_start = datetime.combine(new_date, start.time(), tzinfo=start.tzinfo)
        new_end = new_start + duration
        return Visit.objects.create(
            client=self.client,
            scheduled_start=new_start,
            scheduled_end=new_end,
            cloned_from=self,
            business_service=self.business_service,
            notes=f'Cloned from visit on {start:%Y-%m-%d}',
        )

    @property
    def duration_hours(self) -> float:
        return (self.scheduled_end - self.scheduled_start).total_seconds() / 3600

    @property
    def schedule_display(self) -> str:
        start = timezone.localtime(self.scheduled_start)
        end = timezone.localtime(self.scheduled_end)
        if start.date() == end.date():
            return f'{start:%b %d, %Y} {start:%I:%M %p} – {end:%I:%M %p}'
        return f'{start:%b %d, %Y} {start:%I:%M %p} – {end:%b %d, %Y} {end:%I:%M %p}'

    @property
    def is_editable(self) -> bool:
        return self.status == self.Status.SCHEDULED

    @property
    def accepts_timeline_events(self) -> bool:
        return self.status == self.Status.CHECKED_IN

    @property
    def service_slug(self) -> str:
        service = self.business_service
        return service.slug if service is not None else ''

    @property
    def is_meet_greet_visit(self) -> bool:
        from operations.services.pipeline import MEET_GREET_SLUG

        return self.service_slug == MEET_GREET_SLUG

    @property
    def is_evaluation_visit(self) -> bool:
        from operations.services.pipeline import INITIAL_EVALUATION_SLUG

        return self.service_slug == INITIAL_EVALUATION_SLUG

    @property
    def needs_evaluation_outcome(self) -> bool:
        return (
            self.is_evaluation_visit
            and self.status == self.Status.COMPLETED
            and not self.evaluation_outcome
        )

    @property
    def needs_meet_greet_outcome(self) -> bool:
        return (
            self.is_meet_greet_visit
            and self.status == self.Status.COMPLETED
            and not self.meet_greet_outcome
        )
