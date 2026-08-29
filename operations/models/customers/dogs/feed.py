from django.urls import reverse


class DogFeedMixin:
    """Customer photo feed credentials, slug syncing, and URL formatting."""

    def ensure_feed_credentials(self, *, save: bool = True):
        # Leaf import adhering to PHILOSOPHY.md §5
        from operations.services.feed_interactions.slugs import (
            dog_slug_from_name,
            generate_unique_feed_secret,
        )

        update_fields = []
        if not self.feed_dog_slug:
            self.feed_dog_slug = dog_slug_from_name(self.dog_name)
            update_fields.append('feed_dog_slug')
        if not self.feed_secret:
            self.feed_secret = generate_unique_feed_secret()
            update_fields.append('feed_secret')
        if update_fields and save:
            update_fields.append('updated_at')
            self.save(update_fields=update_fields)
        return self

    def sync_feed_dog_slug(self, *, save: bool = True) -> None:
        from operations.services.feed_interactions.slugs import dog_slug_from_name

        slug = dog_slug_from_name(self.dog_name)
        if self.feed_dog_slug != slug:
            self.feed_dog_slug = slug
            if save:
                self.save(update_fields=['feed_dog_slug', 'updated_at'])

    def regenerate_feed_secret(self, *, save: bool = True) -> str:
        from operations.services.feed_interactions.slugs import (
            dog_slug_from_name,
            generate_unique_feed_secret,
        )

        self.feed_secret = generate_unique_feed_secret()
        if not self.feed_dog_slug:
            self.feed_dog_slug = dog_slug_from_name(self.dog_name)
        if save:
            self.save(update_fields=['feed_secret', 'feed_dog_slug', 'updated_at'])
        return self.feed_secret

    def feed_url_path(self, *, create: bool = True) -> str:
        if create:
            self.ensure_feed_credentials()
        if not self.feed_secret or not self.feed_dog_slug:
            return ''
        return reverse(
            'operations:customer_feed',
            kwargs={
                'feed_secret': self.feed_secret,
                'feed_dog_slug': self.feed_dog_slug,
            },
        )

    def feed_url(self, *, request=None, create: bool = True) -> str:
        path = self.feed_url_path(create=create)
        if not path:
            return ''
        if request is not None:
            return request.build_absolute_uri(path)
        from django.conf import settings

        base = getattr(settings, 'PUBLIC_SITE_URL', '').rstrip('/')
        return f'{base}{path}' if base else path
