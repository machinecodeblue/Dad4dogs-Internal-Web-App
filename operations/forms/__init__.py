"""
Domain-grouped forms for operations.

Import from here as usual: from operations.forms import VisitForm
"""
from operations.forms.business import BusinessProfileForm
from operations.forms.customers import CustomerOwnerForm, DogProfileForm, VaccinationRecordForm
from operations.forms.scheduling import TimelineForwardForm, TimelineMomentForm, VisitForm, VisitScheduleForm

__all__ = [
    'BusinessProfileForm',
    'CustomerOwnerForm',
    'DogProfileForm',
    'VaccinationRecordForm',
    'TimelineForwardForm',
    'TimelineMomentForm',
    'VisitForm',
    'VisitScheduleForm',
]