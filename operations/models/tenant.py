import uuid

from django.db import models


class Workspace(models.Model):
    """
    Pure tenant root: identity and boundary only.

    Do not add phones, hours, capacity, billing IDs, or orchestration methods here.
    Brand/contact → BusinessProfile; capacity numbers → CapacitySettings; logic → services.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    slug = models.SlugField(max_length=100, unique=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'workspace'
        verbose_name_plural = 'workspaces'

    def __str__(self):
        return self.slug
