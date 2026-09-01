from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client as DjangoTestClient, TestCase
from django.urls import reverse
from django.utils import timezone

from operations.models import (
    ClientProfile,
    FeedAccessLog,
    MediaComment,
    MediaReaction,
    SharedMediaLink,
    Visit,
)
from operations.services.feed_interactions import (
    VISITOR_COOKIE_NAME,
    add_comment,
    dog_slug_from_name,
    generate_feed_secret,
    get_or_create_share_link,
    set_reaction,
)
from operations.services.timeline_media import log_moment_for_visits
from operations.tests.conftest import test_image_file


class FeedSlugTests(TestCase):
    def test_dog_slug_from_name(self):
        self.assertEqual(dog_slug_from_name('Lulu'), 'lulu')
        self.assertEqual(dog_slug_from_name('Mr. Biscuit'), 'mr-biscuit')

    def test_generate_feed_secret_is_speakable(self):
        consonants = set('bcdfghjklmnprstvwz')
        vowels = set('aeiou')
        secret = generate_feed_secret()
        self.assertGreaterEqual(len(secret), 8)
        self.assertTrue(secret.isalpha())
        self.assertEqual(secret, secret.lower())
        for index, char in enumerate(secret):
            if index % 2 == 0:
                self.assertIn(char, consonants)
            else:
                self.assertIn(char, vowels)

    def test_ensure_feed_credentials_on_client(self):
        dog = ClientProfile.objects.create(
            dog_name='Lulu',
            owner_name='Jane',
            owner_email='jane@example.com',
        )
        dog.ensure_feed_credentials()
        self.assertTrue(dog.feed_secret)
        self.assertEqual(dog.feed_dog_slug, 'lulu')
        self.assertIn('/feed/', dog.feed_url_path())

    def test_regenerate_feed_secret_changes_link(self):
        dog = ClientProfile.objects.create(
            dog_name='Lulu',
            owner_name='Jane',
            owner_email='jane@example.com',
        )
        dog.ensure_feed_credentials()
        old_secret = dog.feed_secret
        dog.regenerate_feed_secret()
        self.assertNotEqual(dog.feed_secret, old_secret)
        self.assertEqual(dog.feed_dog_slug, 'lulu')


class CustomerFeedTests(TestCase):
    def setUp(self):
        self.dog = ClientProfile.objects.create(
            dog_name='Lulu',
            owner_name='Jane',
            owner_email='jane@example.com',
        )
        self.dog.ensure_feed_credentials()
        self.visit = Visit.objects.create(
            client=self.dog,
            scheduled_start=timezone.now(),
            scheduled_end=timezone.now() + timedelta(hours=4),
            status=Visit.Status.CHECKED_IN,
            actual_arrival=timezone.now(),
        )
        self.client = DjangoTestClient()

    def test_customer_feed_requires_matching_dog_slug(self):
        url = reverse(
            'operations:customer_feed',
            kwargs={
                'feed_secret': self.dog.feed_secret,
                'feed_dog_slug': 'wrong-dog',
            },
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

    def test_customer_feed_sets_visitor_cookie_and_logs_access(self):
        url = reverse(
            'operations:customer_feed',
            kwargs={
                'feed_secret': self.dog.feed_secret,
                'feed_dog_slug': self.dog.feed_dog_slug,
            },
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn('Lulu', response.content.decode())
        self.assertNotIn('bottom-nav', response.content.decode())
        self.assertEqual(response.headers.get('X-Robots-Tag'), 'noindex, nofollow')
        self.assertIn(VISITOR_COOKIE_NAME, response.cookies)
        self.assertEqual(FeedAccessLog.objects.filter(client=self.dog).count(), 1)

    def test_customer_feed_shows_timeline_event(self):
        _, events = log_moment_for_visits(
            visits=[self.visit],
            media_kind='photo',
            uploaded_file=test_image_file(),
            caption_notes='Sunny nap',
            latitude=Decimal('43.01'),
            longitude=Decimal('-81.23'),
            used_fallback=False,
            fallback_label='',
        )
        self.assertEqual(len(events), 1)
        url = reverse(
            'operations:customer_feed',
            kwargs={
                'feed_secret': self.dog.feed_secret,
                'feed_dog_slug': self.dog.feed_dog_slug,
            },
        )
        response = self.client.get(url)
        self.assertContains(response, 'Sunny nap')
        self.assertNotIn('-81.23', response.content.decode())


class FeedInteractionTests(TestCase):
    def setUp(self):
        self.dog = ClientProfile.objects.create(
            dog_name='Lulu',
            owner_name='Jane',
            owner_email='jane@example.com',
        )
        self.dog.ensure_feed_credentials()
        self.visit = Visit.objects.create(
            client=self.dog,
            scheduled_start=timezone.now(),
            scheduled_end=timezone.now() + timedelta(hours=4),
            status=Visit.Status.CHECKED_IN,
            actual_arrival=timezone.now(),
        )
        _, self.events = log_moment_for_visits(
            visits=[self.visit],
            media_kind='photo',
            uploaded_file=test_image_file(),
            caption_notes='Nap time',
            latitude=Decimal('43.01'),
            longitude=Decimal('-81.23'),
            used_fallback=False,
            fallback_label='',
        )
        self.asset_id = self.events[0].media_asset_id
        self.client = DjangoTestClient()

    def _feed_react_url(self):
        return reverse(
            'operations:customer_feed_react',
            kwargs={
                'feed_secret': self.dog.feed_secret,
                'feed_dog_slug': self.dog.feed_dog_slug,
                'asset_id': self.asset_id,
            },
        )

    def test_react_and_comment_on_feed(self):
        self.client.post(self._feed_react_url(), {'emoji': MediaReaction.Emoji.LOVE})
        self.assertEqual(MediaReaction.objects.count(), 1)
        comment_url = reverse(
            'operations:customer_feed_comment',
            kwargs={
                'feed_secret': self.dog.feed_secret,
                'feed_dog_slug': self.dog.feed_dog_slug,
                'asset_id': self.asset_id,
            },
        )
        self.client.post(comment_url, {'display_name': 'Mom', 'text': 'So cute!'})
        self.assertEqual(MediaComment.objects.count(), 1)
        feed_url = reverse(
            'operations:customer_feed',
            kwargs={
                'feed_secret': self.dog.feed_secret,
                'feed_dog_slug': self.dog.feed_dog_slug,
            },
        )
        response = self.client.get(feed_url)
        self.assertContains(response, 'So cute!')
        self.assertContains(response, '❤️')

    def test_public_share_link_isolated_from_feed(self):
        link = get_or_create_share_link(client=self.dog, asset_id=self.asset_id)
        self.assertTrue(link.share_token)
        share_url = reverse('operations:public_feed_share', kwargs={'share_token': link.share_token})
        self.assertIn('/feed/share/', share_url)
        response = self.client.get(share_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Lulu')
        self.assertNotIn('icon-192.png', response.content.decode())
        self.assertContains(response, 'og:image')
        self.assertContains(response, 'twitter:image')
        self.assertNotIn(self.dog.feed_secret, response.content.decode())
        self.assertContains(response, 'share-icon-btn')
        self.assertContains(response, 'comment-icon-btn')
        self.assertContains(response, 'download-icon-btn')
        self.assertContains(response, '/download/')
        self.assertContains(response, f'dad4dogs_{link.id}.jpg')
        self.assertContains(response, 'reaction-bar')
        self.assertNotContains(response, 'comment-panel always-open')
        link.refresh_from_db()
        self.assertEqual(link.view_count, 1)

    def test_public_share_download_filename(self):
        link = get_or_create_share_link(client=self.dog, asset_id=self.asset_id)
        download_url = reverse(
            'operations:public_feed_share_download',
            kwargs={'share_token': link.share_token},
        )
        response = self.client.get(download_url)
        self.assertEqual(response.status_code, 200)
        disposition = response.headers.get('Content-Disposition', '')
        self.assertIn('attachment', disposition)
        self.assertIn(f'dad4dogs_{link.id}.jpg', disposition)
        self.assertNotIn('master_', disposition)

    def test_public_share_react_without_comment(self):
        link = get_or_create_share_link(client=self.dog, asset_id=self.asset_id)
        react_url = reverse(
            'operations:public_feed_share_react',
            kwargs={'share_token': link.share_token},
        )
        self.client.post(react_url, {'emoji': MediaReaction.Emoji.LOVE})
        share_url = reverse('operations:public_feed_share', kwargs={'share_token': link.share_token})
        response = self.client.get(share_url)
        self.assertContains(response, '❤️')
        self.assertEqual(MediaComment.objects.count(), 0)

    def test_public_share_react_and_comment(self):
        link = get_or_create_share_link(client=self.dog, asset_id=self.asset_id)
        react_url = reverse(
            'operations:public_feed_share_react',
            kwargs={'share_token': link.share_token},
        )
        self.client.post(react_url, {'emoji': MediaReaction.Emoji.LOVE})
        self.assertEqual(MediaReaction.objects.count(), 1)

        comment_url = reverse(
            'operations:public_feed_share_comment',
            kwargs={'share_token': link.share_token},
        )
        self.client.post(comment_url, {'display_name': 'Friend', 'text': 'Adorable!'})
        self.assertEqual(MediaComment.objects.count(), 1)

        link.refresh_from_db()
        views_before = link.view_count
        self.client.post(react_url, {'emoji': MediaReaction.Emoji.LIKE})
        link.refresh_from_db()
        self.assertEqual(link.view_count, views_before)

        share_url = reverse('operations:public_feed_share', kwargs={'share_token': link.share_token})
        response = self.client.get(share_url)
        self.assertContains(response, 'Adorable!')
        self.assertContains(response, '❤️')
        self.assertContains(response, 'Friend')
        link.refresh_from_db()
        self.assertEqual(link.view_count, views_before + 1)

    def test_customer_feed_has_compact_share_icon(self):
        feed_url = reverse(
            'operations:customer_feed',
            kwargs={
                'feed_secret': self.dog.feed_secret,
                'feed_dog_slug': self.dog.feed_dog_slug,
            },
        )
        response = self.client.get(feed_url)
        self.assertContains(response, 'share-icon-btn')
        self.assertContains(response, 'comment-icon-btn')
        self.assertContains(response, '/feed/share/')
        self.assertNotContains(response, 'Share this moment with friends')
        self.assertContains(response, '🐾')

    def test_checkin_feed_activity_requires_login(self):
        url = reverse('operations:checkin_feed_activity')
        self.assertEqual(self.client.get(url).status_code, 302)

    def test_checkin_feed_activity_returns_comment(self):
        user = get_user_model().objects.create_user('david', 'd@example.com', 'pass')
        self.client.force_login(user)
        comment_url = reverse(
            'operations:customer_feed_comment',
            kwargs={
                'feed_secret': self.dog.feed_secret,
                'feed_dog_slug': self.dog.feed_dog_slug,
                'asset_id': self.asset_id,
            },
        )
        self.client.post(comment_url, {'display_name': 'Mom', 'text': 'Love this!'})
        activity_url = reverse('operations:checkin_feed_activity')
        response = self.client.get(activity_url)
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        dog_bucket = payload['dogs'][str(self.dog.pk)]
        self.assertEqual(dog_bucket['dog_name'], 'Lulu')
        self.assertTrue(any(item['text'] == 'Love this!' for item in dog_bucket['items']))