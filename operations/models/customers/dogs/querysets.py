from datetime import timedelta

from django.db import models
from django.db.models import Count, Max, Q
from django.utils import timezone

from operations.models.customers.constants import (
    VAX_EXPIRY_WARNING_DAYS,
    VAX_STATUS_EXPIRED,
    VAX_STATUS_EXPIRING,
    VAX_STATUS_MISSING,
    VAX_STATUS_OK,
)


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
