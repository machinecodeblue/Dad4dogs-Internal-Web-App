from datetime import date, datetime
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client as DjangoTestClient, TestCase
from django.urls import reverse
from django.utils import timezone

from operations.forms import TimelineMomentForm
from operations.models import (
    ClientProfile,
    TimelineMediaAsset,
    Visit,
    VisitTimelineEvent,
)
from operations.models.scheduling import timeline_asset_upload_path
from operations.services.timeline_media import (
    TimelineMediaError,
    create_photo_asset,
    create_video_asset,
    forward_timeline_event,
    log_moment_for_visits,
)
from operations.tests.conftest import TZ, test_image_file


class TimelineMomentFormTests(TestCase):
    def setUp(self):
        self.dog = ClientProfile.objects.create(
            dog_name='Rex',
            owner_name='Jane Doe',
            owner_email='jane@example.com',
        )
        self.visit = Visit.objects.create(
            client=self.dog,
            scheduled_start=datetime(2026, 7, 6, 9, 0, tzinfo=TZ),
            scheduled_end=datetime(2026, 7, 6, 17, 0, tzinfo=TZ),
            status=Visit.Status.CHECKED_IN,
        )

    def test_requires_single_media_type(self):
        form = TimelineMomentForm(
            data={'caption_notes': 'Playing fetch', 'visit_ids': [str(self.visit.pk)]},
            files={
                'photo_gallery': test_image_file(),
                'video': test_image_file('clip.mp4'),
            },
            eligible_visits=Visit.objects.filter(pk=self.visit.pk),
        )
        self.assertFalse(form.is_valid())

    def test_rejects_camera_and_gallery_together(self):
        form = TimelineMomentForm(
            data={'caption_notes': 'Two photos', 'visit_ids': [str(self.visit.pk)]},
            files={
                'photo_camera': test_image_file('cam.jpg'),
                'photo_gallery': test_image_file('gal.jpg'),
            },
            eligible_visits=Visit.objects.filter(pk=self.visit.pk),
        )
        self.assertFalse(form.is_valid())
        self.assertIn('not both', str(form.errors).lower())

    def test_accepts_gallery_photo_only(self):
        form = TimelineMomentForm(
            data={
                'caption_notes': 'Nap time',
                'latitude': '43.0',
                'longitude': '-81.2',
                'visit_ids': [str(self.visit.pk)],
            },
            files={'photo_gallery': test_image_file()},
            eligible_visits=Visit.objects.filter(pk=self.visit.pk),
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['media_kind'], 'photo')
        self.assertEqual(form.cleaned_data['latitude'], Decimal('43.0'))
        self.assertEqual(form.cleaned_data['longitude'], Decimal('-81.2'))

    def test_blank_coordinates_are_allowed(self):
        form = TimelineMomentForm(
            data={'caption_notes': '', 'visit_ids': [str(self.visit.pk)]},
            files={'photo_gallery': test_image_file()},
            eligible_visits=Visit.objects.filter(pk=self.visit.pk),
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['latitude'], '')
        self.assertEqual(form.cleaned_data['longitude'], '')

    def test_rejects_non_numeric_coordinates(self):
        form = TimelineMomentForm(
            data={
                'caption_notes': '',
                'visit_ids': [str(self.visit.pk)],
                'latitude': 'north',
                'longitude': '-81.2',
            },
            files={'photo_gallery': test_image_file()},
            eligible_visits=Visit.objects.filter(pk=self.visit.pk),
        )
        self.assertFalse(form.is_valid())
        self.assertIn('latitude', form.errors)

    def test_rejects_out_of_range_coordinates(self):
        form = TimelineMomentForm(
            data={
                'caption_notes': '',
                'visit_ids': [str(self.visit.pk)],
                'latitude': '91',
                'longitude': '-81.2',
            },
            files={'photo_gallery': test_image_file()},
            eligible_visits=Visit.objects.filter(pk=self.visit.pk),
        )
        self.assertFalse(form.is_valid())
        self.assertIn('latitude', form.errors)

    def test_rejects_latitude_without_longitude(self):
        form = TimelineMomentForm(
            data={
                'caption_notes': '',
                'visit_ids': [str(self.visit.pk)],
                'latitude': '43.0',
            },
            files={'photo_gallery': test_image_file()},
            eligible_visits=Visit.objects.filter(pk=self.visit.pk),
        )
        self.assertFalse(form.is_valid())
        self.assertIn('longitude', form.errors)


class VisitTimelineTests(TestCase):
    def setUp(self):
        self._today_patch = patch(
            'operations.services.timeline_visits.timezone.localdate',
            return_value=date(2026, 7, 6),
        )
        self._today_patch.start()
        self.addCleanup(self._today_patch.stop)
        self.user = get_user_model().objects.create_user(username='david', password='testpass123')
        self.client = DjangoTestClient()
        self.client.login(username='david', password='testpass123')
        self.dog = ClientProfile.objects.create(
            dog_name='Rex',
            owner_name='Jane Doe',
            owner_email='jane@example.com',
        )
        self.dog_two = ClientProfile.objects.create(
            dog_name='Bailey',
            owner_name='John Doe',
            owner_email='john@example.com',
        )
        self.visit = Visit.objects.create(
            client=self.dog,
            scheduled_start=datetime(2026, 7, 6, 9, 0, tzinfo=TZ),
            scheduled_end=datetime(2026, 7, 6, 17, 0, tzinfo=TZ),
            status=Visit.Status.CHECKED_IN,
            actual_arrival=datetime(2026, 7, 6, 9, 5, tzinfo=TZ),
        )
        self.visit_two = Visit.objects.create(
            client=self.dog_two,
            scheduled_start=datetime(2026, 7, 6, 9, 0, tzinfo=TZ),
            scheduled_end=datetime(2026, 7, 6, 17, 0, tzinfo=TZ),
            status=Visit.Status.CHECKED_IN,
            actual_arrival=datetime(2026, 7, 6, 9, 10, tzinfo=TZ),
        )

    def test_timeline_blocked_when_not_checked_in(self):
        self.visit.status = Visit.Status.SCHEDULED
        self.visit.save()
        response = self.client.get(reverse('operations:visit_timeline', args=[self.visit.pk]))
        self.assertEqual(response.status_code, 302)

    def test_timeline_page_renders_for_checked_in_visit(self):
        response = self.client.get(reverse('operations:visit_timeline', args=[self.visit.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Log Moment')
        self.assertContains(response, 'capture="environment"', html=False)
        self.assertContains(response, 'Choose Photo (gallery)')

    def test_timeline_get_does_not_query_forward_targets_per_event(self):
        for caption in ('One', 'Two', 'Three'):
            log_moment_for_visits(
                visits=[self.visit],
                media_kind='photo',
                uploaded_file=test_image_file(),
                caption_notes=caption,
                latitude=Decimal('43.01'),
                longitude=Decimal('-81.23'),
                used_fallback=False,
                fallback_label='',
            )
        with patch('operations.views.scheduling.timeline.visits_available_for_forward') as mock_fwd:
            response = self.client.get(
                reverse('operations:visit_timeline', args=[self.visit.pk]),
            )
        self.assertEqual(response.status_code, 200)
        mock_fwd.assert_not_called()

    def test_invalid_moment_flashes_plain_error(self):
        from django.contrib.messages import get_messages

        response = self.client.post(
            reverse('operations:visit_timeline', args=[self.visit.pk]),
            {'caption_notes': '', 'visit_ids': [str(self.visit.pk)]},
        )
        self.assertEqual(response.status_code, 302)
        text = ' '.join(str(m) for m in get_messages(response.wsgi_request))
        self.assertNotIn('*', text)
        self.assertNotIn('visit_ids', text)
        self.assertTrue(text)
        self.assertRegex(text.lower(), r'photo|video|capture')

    def test_invalid_forward_flashes_plain_error(self):
        from django.contrib.messages import get_messages

        _, events = log_moment_for_visits(
            visits=[self.visit],
            media_kind='photo',
            uploaded_file=test_image_file(),
            caption_notes='Share me',
            latitude=Decimal('43.01'),
            longitude=Decimal('-81.23'),
            used_fallback=False,
            fallback_label='',
        )
        response = self.client.post(
            reverse(
                'operations:visit_timeline_forward',
                args=[self.visit.pk, events[0].pk],
            ),
            {},
        )
        self.assertEqual(response.status_code, 302)
        text = ' '.join(str(m) for m in get_messages(response.wsgi_request))
        self.assertNotIn('*', text)
        self.assertNotIn('visit_ids', text)
        self.assertIn('Share with', text)

    def test_create_photo_asset_pipeline(self):
        asset = create_photo_asset(
            uploaded_file=test_image_file(),
            caption_notes='Zoomies in the yard',
            latitude=Decimal('43.010000'),
            longitude=Decimal('-81.230000'),
            used_fallback=False,
            fallback_label='',
            original_visit=self.visit,
        )
        self.assertEqual(asset.media_type, 'photo')
        self.assertTrue(asset.photo_high_res.name.endswith('.jpg'))
        self.assertTrue(asset.photo_thumbnail.name.endswith('.webp'))
        self.assertRegex(
            asset.photo_high_res.name,
            r'^timeline/assets/\d{4}/\d{2}/\d{2}/master_.+\.jpg$',
        )
        self.assertNotIn('/new/', asset.photo_high_res.name)
        self.assertRegex(
            asset.photo_thumbnail.name,
            r'^timeline/assets/\d{4}/\d{2}/\d{2}/thumb_.+\.webp$',
        )

    def test_post_photo_moment_for_multiple_dogs(self):
        response = self.client.post(
            reverse('operations:visit_timeline', args=[self.visit.pk]),
            {
                'caption_notes': 'Pack photo',
                'latitude': '43.01',
                'longitude': '-81.23',
                'visit_ids': [str(self.visit.pk), str(self.visit_two.pk)],
                'photo_gallery': test_image_file(),
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.visit.timeline_events.count(), 1)
        self.assertEqual(self.visit_two.timeline_events.count(), 1)
        asset = self.visit.timeline_events.first().media_asset
        self.assertEqual(self.visit_two.timeline_events.first().media_asset_id, asset.pk)

    def test_forward_view_post(self):
        _, events = log_moment_for_visits(
            visits=[self.visit],
            media_kind='photo',
            uploaded_file=test_image_file(),
            caption_notes='Share me',
            latitude=Decimal('43.01'),
            longitude=Decimal('-81.23'),
            used_fallback=False,
            fallback_label='',
        )
        response = self.client.post(
            reverse(
                'operations:visit_timeline_forward',
                args=[self.visit.pk, events[0].pk],
            ),
            {'visit_ids': [str(self.visit_two.pk)]},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.visit_two.timeline_events.count(), 1)

    def test_forward_preserves_capture_time(self):
        _, events = log_moment_for_visits(
            visits=[self.visit],
            media_kind='photo',
            uploaded_file=test_image_file(),
            caption_notes='Yard time',
            latitude=Decimal('43.01'),
            longitude=Decimal('-81.23'),
            used_fallback=False,
            fallback_label='',
        )
        source = events[0]
        captured = source.captured_at
        forwarded = forward_timeline_event(
            source_event=source,
            target_visit_ids=[self.visit_two.pk],
        )
        self.assertEqual(forwarded[0].captured_at, captured)
        self.assertTrue(forwarded[0].is_forward)

    def test_forward_blocked_after_checkout(self):
        _, events = log_moment_for_visits(
            visits=[self.visit],
            media_kind='photo',
            uploaded_file=test_image_file(),
            caption_notes='',
            latitude=Decimal('43.01'),
            longitude=Decimal('-81.23'),
            used_fallback=False,
            fallback_label='',
        )
        self.visit_two.status = Visit.Status.COMPLETED
        self.visit_two.save()
        with self.assertRaises(TimelineMediaError):
            forward_timeline_event(
                source_event=events[0],
                target_visit_ids=[self.visit_two.pk],
            )

    def test_reject_oversized_video(self):
        huge = SimpleUploadedFile('big.mp4', b'x' * (26 * 1024 * 1024), content_type='video/mp4')
        with self.assertRaises(TimelineMediaError):
            create_video_asset(
                uploaded_file=huge,
                caption_notes='',
                latitude=Decimal('43.0'),
                longitude=Decimal('-81.2'),
                used_fallback=False,
                fallback_label='',
                original_visit=self.visit,
            )


class TimelineUploadPathTests(TestCase):
    def test_uses_captured_at_date_not_pk_or_new(self):
        class Dummy:
            pk = None
            captured_at = datetime(2026, 8, 23, 15, 0, tzinfo=TZ)

        path = timeline_asset_upload_path(Dummy(), 'master_abc.jpg')
        self.assertEqual(path, 'timeline/assets/2026/08/23/master_abc.jpg')

    def test_falls_back_to_now_when_captured_at_missing(self):
        class Dummy:
            pk = None
            captured_at = None

        frozen = datetime(2026, 1, 2, 12, 0, tzinfo=TZ)
        with patch('operations.models.scheduling.timezone.now', return_value=frozen):
            path = timeline_asset_upload_path(Dummy(), 'thumb.webp')
        self.assertEqual(path, 'timeline/assets/2026/01/02/thumb.webp')
        self.assertNotIn('/new/', path)


class TimelineMediaAssetCapturedAtTests(TestCase):
    def setUp(self):
        dog = ClientProfile.objects.create(
            dog_name='Rex',
            owner_name='Jane Doe',
            owner_email='jane@example.com',
        )
        self.visit = Visit.objects.create(
            client=dog,
            scheduled_start=datetime(2026, 8, 23, 9, 0, tzinfo=TZ),
            scheduled_end=datetime(2026, 8, 23, 17, 0, tzinfo=TZ),
        )

    def _create(self, **kwargs):
        defaults = {
            'media_type': TimelineMediaAsset.MediaType.PHOTO,
            'latitude': Decimal('43.01'),
            'longitude': Decimal('-81.23'),
            'original_visit': self.visit,
        }
        defaults.update(kwargs)
        return TimelineMediaAsset.objects.create(**defaults)

    def test_captured_at_defaults_when_omitted(self):
        before = timezone.now()
        asset = self._create()
        after = timezone.now()
        self.assertIsNotNone(asset.captured_at)
        self.assertGreaterEqual(asset.captured_at, before)
        self.assertLessEqual(asset.captured_at, after)

    def test_explicit_captured_at_is_kept(self):
        when = datetime(2026, 4, 11, 9, 0, tzinfo=TZ)
        asset = self._create(captured_at=when)
        asset.refresh_from_db()
        self.assertEqual(asset.captured_at, when)