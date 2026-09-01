from .test_agenda import AgendaTests, DashboardViewTests, DatetimeParseTests
from .test_calendar import GmailSendTests, PendingEventApproveTests, VisitEmailTests
from .test_capacity import CapacityTimezoneTests, VisitCapacitySaveTests
from .test_checkin import VisitCheckInOutViewTests, VisitCheckOutTests
from .test_pricing import PricingEngineTests
from .test_visits import (
    VisitCloneToDateTests,
    VisitFormTests,
    VisitIndexTests,
    VisitRepeatTests,
)

__all__ = [
    'AgendaTests',
    'DashboardViewTests',
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
    'PendingEventApproveTests',
]