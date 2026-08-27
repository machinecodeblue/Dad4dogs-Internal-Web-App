from operations.views.services.actions import service_deactivate, service_toggle_active
from operations.views.services.catalog import service_list
from operations.views.services.edit import service_create, service_edit
from operations.views.services.rules import rule_create, rule_delete

__all__ = [
    'service_list',
    'service_create',
    'service_edit',
    'rule_create',
    'rule_delete',
    'service_toggle_active',
    'service_deactivate',
]
