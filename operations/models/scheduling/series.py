from django.db import models
from operations.models.base import TenantAwareModel
from operations.models.customers import ClientProfile


class VisitSeries(TenantAwareModel):
    """Links recurring visits created together (Google Calendar–style repeat)."""
    client = models.ForeignKey(
        ClientProfile,
        on_delete=models.CASCADE,
        related_name='visit_series',
    )
    frequency = models.CharField(max_length=20)
    interval = models.PositiveSmallIntegerField(default=1)
    end_type = models.CharField(max_length=10)
    total_occurrences = models.PositiveSmallIntegerField()
    until = models.DateTimeField(null=True, blank=True)
    anchor_start = models.DateTimeField(
        help_text='Start of the first occurrence (template for the series).',
    )
    anchor_end = models.DateTimeField(
        help_text='End of the first occurrence (template for the series).',
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = 'visit series'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.client.dog_name} — {self.frequency} × {self.total_occurrences}'

    @property
    def label(self) -> str:
        from operations.services.visit_repeat import repeat_summary

        visits = list(self.visits.order_by('scheduled_start'))
        if not visits:
            return f'Repeat ({self.total_occurrences})'
        pairs = [(v.scheduled_start, v.scheduled_end) for v in visits]
        return repeat_summary(pairs, self.frequency, self.interval)