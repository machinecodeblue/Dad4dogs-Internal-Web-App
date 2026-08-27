from django.core.exceptions import ValidationError
from django.db import models


class TenantAwareModel(models.Model):
    """
    Abstract base: every operational row belongs to a Workspace (tenant).

    Phase 1: clean() blocks cross-tenant FK links; save() fills tenant from the
    active workspace bridge when unset. Phase 2 will add default QuerySet filters.
    """

    tenant = models.ForeignKey(
        'operations.Workspace',
        on_delete=models.CASCADE,
        related_name='%(app_label)s_%(class)s_set',
        db_index=True,
        null=True,
        blank=True,
    )

    class Meta:
        abstract = True

    def clean(self):
        super().clean()
        if not self.tenant_id:
            return
        for field in self._meta.fields:
            if not field.is_relation or field.many_to_many or field.auto_created:
                continue
            if field.name == 'tenant':
                continue
            related = getattr(self, field.name, None)
            if related is None:
                continue
            related_tenant_id = getattr(related, 'tenant_id', None)
            if related_tenant_id is None and hasattr(related, 'workspace_id'):
                related_tenant_id = related.workspace_id
            if related_tenant_id is not None and related_tenant_id != self.tenant_id:
                raise ValidationError(
                    {
                        field.name: (
                            f'Tenant isolation violation: {field.name} belongs to a '
                            f'different workspace.'
                        ),
                    },
                )

    def save(self, *args, **kwargs):
        if not self.tenant_id:
            from operations.services.context_tenant import get_active_workspace

            self.tenant = get_active_workspace()
        super().save(*args, **kwargs)
