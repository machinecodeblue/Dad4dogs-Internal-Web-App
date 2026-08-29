VAX_EXPIRY_WARNING_DAYS = 30

VAX_STATUS_OK = 'ok'
VAX_STATUS_EXPIRING = 'expiring'
VAX_STATUS_EXPIRED = 'expired'
VAX_STATUS_MISSING = 'missing'

VAX_FILTER_CHOICES = (
    (VAX_STATUS_EXPIRING, 'Expiring (30 days)'),
    (VAX_STATUS_EXPIRED, 'Expired'),
    (VAX_STATUS_MISSING, 'No validated record'),
    (VAX_STATUS_OK, 'Current (30+ days)'),
)