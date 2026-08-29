"""
Domain-grouped forms for operations.

Import from here as usual: from operations.forms import VisitForm
"""
from operations.forms.business import BusinessProfileForm
from operations.forms.customers import CustomerOwnerForm, DogProfileForm, VaccinationRecordForm
from operations.forms.evaluation import EvaluationOutcomeForm, MeetGreetOutcomeForm
from operations.forms.intake import (
    EvaluationScheduleForm,
    IntakeWizardForm,
    MeetGreetScheduleForm,
)
from operations.forms.scheduling import TimelineForwardForm, TimelineMomentForm, VisitForm, VisitScheduleForm
from operations.forms.services import BusinessServiceForm, ServiceBehaviorRuleForm

__all__ = [
    'BusinessProfileForm',
    'BusinessServiceForm',
    'CustomerOwnerForm',
    'DogProfileForm',
    'EvaluationOutcomeForm',
    'MeetGreetOutcomeForm',
    'EvaluationScheduleForm',
    'IntakeWizardForm',
    'MeetGreetScheduleForm',
    'ServiceBehaviorRuleForm',
    'VaccinationRecordForm',
    'TimelineForwardForm',
    'TimelineMomentForm',
    'VisitForm',
    'VisitScheduleForm',
]
