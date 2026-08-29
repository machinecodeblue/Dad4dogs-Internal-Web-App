from django.db import models
from operations.models.base import TenantAwareModel
from .dogs import ClientProfile


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