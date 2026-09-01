from .customers.test_compliance import AddressHandlingTests, ComplianceTests, VaccinationExpiryViewTests
from .customers.test_contacts import ContactDataTests, ContactSyncTests, NeedsDogNameTests
from .customers.test_forms import CustomerOwnerFormTests, DogProfileFormTests
from .customers.test_intake import IntakeWizardTests, PipelinePhase2Tests
from .customers.test_views import CognitiveLoadUXTests, CustomerEditTests, CustomerViewsHttpTests

from .scheduling.test_agenda import AgendaTests, DashboardViewTests, DatetimeParseTests
from .scheduling.test_calendar import GmailSendTests, PendingEventApproveTests, VisitEmailTests
from .scheduling.test_capacity import CapacityTimezoneTests, VisitCapacitySaveTests
from .scheduling.test_checkin import VisitCheckInOutViewTests, VisitCheckOutTests
from .scheduling.test_pricing import PricingEngineTests
from .scheduling.test_visits import VisitCloneToDateTests, VisitFormTests, VisitIndexTests, VisitRepeatTests

from .feed.test_interactions import CustomerFeedTests, FeedInteractionTests, FeedSlugTests
from .feed.test_pwa import (
    BusinessProfileTests,
    BusinessSettingsViewTests,
    GeolocationTests,
    PwaTests,
    StatementBillingTests,
)
from .feed.test_timeline import (
    TimelineMediaAssetCapturedAtTests,
    TimelineMomentFormTests,
    TimelineUploadPathTests,
    VisitTimelineTests,
)

__all__ = [
    'CustomerOwnerFormTests',
    'AddressHandlingTests',
    'CognitiveLoadUXTests',
    'IntakeWizardTests',
    'DogProfileFormTests',
    'ContactSyncTests',
    'NeedsDogNameTests',
    'ContactDataTests',
    'CustomerEditTests',
    'CustomerViewsHttpTests',
    'ComplianceTests',
    'VaccinationExpiryViewTests',
    'AgendaTests',
    'DatetimeParseTests',
    'VisitRepeatTests',
    'VisitFormTests',
    'PricingEngineTests',
    'VisitEmailTests',
    'GmailSendTests',
    'VisitCheckOutTests',
    'VisitCapacitySaveTests',
    'CapacityTimezoneTests',
    'VisitIndexTests',
    'VisitCloneToDateTests',
    'VisitCheckInOutViewTests',
    'DashboardViewTests',
    'PendingEventApproveTests',
    'BusinessProfileTests',
    'BusinessSettingsViewTests',
    'PwaTests',
    'GeolocationTests',
    'TimelineMomentFormTests',
    'VisitTimelineTests',
    'TimelineUploadPathTests',
    'TimelineMediaAssetCapturedAtTests',
    'FeedSlugTests',
    'CustomerFeedTests',
    'FeedInteractionTests',
    'StatementBillingTests',
    'PipelinePhase2Tests',
]