from datetime import timedelta

from django.utils import timezone

from operations.models.customers.constants import (
    VAX_EXPIRY_WARNING_DAYS,
    VAX_STATUS_EXPIRED,
    VAX_STATUS_EXPIRING,
    VAX_STATUS_MISSING,
    VAX_STATUS_OK,
)


class DogVaccinationMixin:
    """Vaccination computation, expiry queries, and status resolution."""

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
