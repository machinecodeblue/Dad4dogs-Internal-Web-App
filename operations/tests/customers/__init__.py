from .test_compliance import AddressHandlingTests, ComplianceTests, VaccinationExpiryViewTests
from .test_contacts import ContactDataTests, ContactSyncTests, NeedsDogNameTests
from .test_forms import CustomerOwnerFormTests, DogProfileFormTests
from .test_intake import IntakeWizardTests, PipelinePhase2Tests
from .test_views import CognitiveLoadUXTests, CustomerEditTests, CustomerViewsHttpTests

__all__ = [
    'CustomerOwnerFormTests',
    'DogProfileFormTests',
    'CognitiveLoadUXTests',
    'CustomerEditTests',
    'CustomerViewsHttpTests',
    'AddressHandlingTests',
    'ComplianceTests',
    'VaccinationExpiryViewTests',
    'ContactSyncTests',
    'NeedsDogNameTests',
    'ContactDataTests',
    'IntakeWizardTests',
    'PipelinePhase2Tests',
]