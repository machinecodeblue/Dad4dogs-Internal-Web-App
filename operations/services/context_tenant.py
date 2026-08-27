"""Single-operator workspace bridge until multi-tenant auth exists."""

from operations.models.tenant import Workspace

ACTIVE_WORKSPACE_SLUG = 'dad4dogs'


def get_active_workspace() -> Workspace:
    """
    Temporary single-operator bridge.

    Ensures the Dad4dogs workspace plus profile and capacity_settings rows exist.
    """
    workspace, _ = Workspace.objects.get_or_create(
        slug=ACTIVE_WORKSPACE_SLUG,
        defaults={'is_active': True},
    )

    from operations.models.business import BusinessProfile, CapacitySettings

    BusinessProfile.objects.get_or_create(
        workspace=workspace,
        defaults={'business_name': 'Dad4dogs'},
    )
    CapacitySettings.objects.get_or_create(workspace=workspace)
    return workspace
