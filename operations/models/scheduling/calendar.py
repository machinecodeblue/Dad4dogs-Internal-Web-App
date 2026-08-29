from django.db import models
from operations.models.base import TenantAwareModel
from operations.models.customers import ClientProfile


class PendingCalendarEvent(TenantAwareModel):
    class ReviewStatus(models.TextChoices):
        PENDING = 'pending', 'Pending Review'
        APPROVED = 'approved', 'Approved'
        REJECTED = 'rejected', 'Rejected'

    event_uid = models.CharField(max_length=255, unique=True)
    summary = models.CharField(max_length=500)
    description = models.TextField(blank=True)
    start_datetime = models.DateTimeField()
    end_datetime = models.DateTimeField()
    matched_client = models.ForeignKey(
        ClientProfile,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    review_status = models.CharField(
        max_length=20,
        choices=ReviewStatus.choices,
        default=ReviewStatus.PENDING,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-start_datetime']

    def __str__(self):
        return self.summary