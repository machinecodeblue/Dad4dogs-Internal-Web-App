from decimal import Decimal

from django.db import models

from .customers import ClientProfile


class AccountStatement(models.Model):
    class SendStatus(models.TextChoices):
        DRAFT = 'draft', 'Draft'
        QUEUED = 'queued', 'Queued for Send'
        SENT = 'sent', 'Sent'

    client = models.ForeignKey(ClientProfile, on_delete=models.CASCADE, related_name='statements')
    week_start = models.DateField()
    week_end = models.DateField()
    line_items = models.JSONField(default=list)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    send_status = models.CharField(max_length=20, choices=SendStatus.choices, default=SendStatus.DRAFT)
    sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-week_start']
        constraints = [
            models.UniqueConstraint(
                fields=['client', 'week_start'],
                name='unique_client_week_statement',
            ),
        ]

    def __str__(self):
        return f'{self.client.dog_name} — week of {self.week_start}'