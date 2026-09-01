from datetime import date, datetime

from django.contrib.auth import get_user_model
from django.test import Client as DjangoTestClient, TestCase
from django.urls import reverse
from django.utils import timezone

from operations.models import ClientProfile, Visit
from operations.services.agenda import build_month_calendar, visit_counts_between, visits_for_day
from operations.services.datetime_parse import format_datetime_display, parse_datetime_text
from operations.tests.conftest import TZ


class AgendaTests(TestCase):
    def setUp(self):
        self.dog = ClientProfile.objects.create(
            dog_name='Winston',
            owner_name='Alexa Green',
            owner_email='alexagreen4@outlook.com',
        )

    def test_visits_for_day_includes_overnight_span(self):
        Visit.objects.create(
            client=self.dog,
            scheduled_start=datetime(2026, 4, 10, 13, 0, tzinfo=TZ),
            scheduled_end=datetime(2026, 4, 11, 1, 0, tzinfo=TZ),
        )
        day10 = visits_for_day(date(2026, 4, 10))
        day11 = visits_for_day(date(2026, 4, 11))
        self.assertEqual(day10.count(), 1)
        self.assertEqual(day11.count(), 1)

    def test_visit_counts_by_day(self):
        Visit.objects.create(
            client=self.dog,
            scheduled_start=datetime(2026, 4, 10, 9, 0, tzinfo=TZ),
            scheduled_end=datetime(2026, 4, 10, 17, 0, tzinfo=TZ),
        )
        counts = visit_counts_between(date(2026, 4, 1), date(2026, 4, 30))
        self.assertEqual(counts[date(2026, 4, 10)], 1)
        self.assertEqual(counts[date(2026, 4, 11)], 0)

    def test_build_month_calendar_marks_selected_day(self):
        weeks = build_month_calendar(2026, 4, date(2026, 4, 10), date(2026, 4, 5))
        flat = [cell for week in weeks for cell in week if cell]
        selected = [cell for cell in flat if cell['is_selected']]
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0]['day'], 10)


class DatetimeParseTests(TestCase):
    def test_parses_natural_start(self):
        dt = parse_datetime_text('April 11th 2026 5 p.m.')
        self.assertEqual(dt.year, 2026)
        self.assertEqual(dt.month, 4)
        self.assertEqual(dt.day, 11)
        self.assertEqual(dt.hour, 17)

    def test_parses_natural_end(self):
        start = parse_datetime_text('April 11, 2026 1 pm')
        end = parse_datetime_text('April 28, 5:00 p.m', default=start)
        self.assertEqual(end.month, 4)
        self.assertEqual(end.day, 28)
        self.assertEqual(end.hour, 17)

    def test_format_display(self):
        dt = parse_datetime_text('April 11, 2026 5 pm')
        self.assertIn('Apr 11, 2026', format_datetime_display(dt))
        self.assertIn('5:00 PM', format_datetime_display(dt))


class DashboardViewTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='david',
            password='testpass123',
        )
        self.client = DjangoTestClient()
        self.client.login(username='david', password='testpass123')

    def test_dashboard_loads(self):
        response = self.client.get(reverse('operations:dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Dad4dogs')

    def test_dashboard_rejects_huge_year(self):
        today = timezone.localdate()
        response = self.client.get(
            reverse('operations:dashboard'),
            {'year': '999999', 'month': '1'},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['cal_year'], today.year)
        self.assertEqual(response.context['cal_month'], today.month)

    def test_dashboard_rejects_year_zero(self):
        today = timezone.localdate()
        response = self.client.get(
            reverse('operations:dashboard'),
            {'year': '0', 'month': '6'},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['cal_year'], today.year)

    def test_dashboard_rejects_post(self):
        response = self.client.post(reverse('operations:dashboard'))
        self.assertEqual(response.status_code, 405)

    def test_parse_datetime_rejects_post(self):
        response = self.client.post(reverse('operations:parse_datetime'))
        self.assertEqual(response.status_code, 405)

    def test_visit_create_rejects_put(self):
        dog = ClientProfile.objects.create(
            dog_name='Rex',
            owner_name='Jane Doe',
            owner_email='jane@example.com',
        )
        response = self.client.put(
            reverse('operations:visit_create', args=[dog.pk]),
        )
        self.assertEqual(response.status_code, 405)