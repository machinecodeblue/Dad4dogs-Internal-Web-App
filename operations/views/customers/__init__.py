from operations.views.customers.actions import (
    advance_pipeline,
    client_add_dog,
    client_detail,
    client_edit,
    dog_delete,
    dog_feed_regenerate,
    dog_hide,
    dog_unhide,
    update_coi,
)
from operations.views.customers.clients import (
    client_list,
    customer_add_dog,
    customer_detail,
    customer_edit,
    dog_detail,
    dog_edit,
)
from operations.views.customers.contacts import (
    client_vcard,
    contact_import_preview,
    contact_import_selected,
    contact_sync,
)
from operations.views.customers.intake import (
    client_create,
    client_intake,
    dog_create_customer,
)
from operations.views.customers.vaccinations import (
    add_vaccination,
    dog_vaccinations,
    validate_vaccination,
)

__all__ = [
    'client_list',
    'customer_detail',
    'dog_detail',
    'customer_edit',
    'dog_edit',
    'customer_add_dog',
    'client_intake',
    'client_create',
    'dog_create_customer',
    'dog_vaccinations',
    'add_vaccination',
    'validate_vaccination',
    'contact_sync',
    'contact_import_preview',
    'contact_import_selected',
    'client_vcard',
    'dog_hide',
    'dog_unhide',
    'advance_pipeline',
    'update_coi',
    'dog_feed_regenerate',
    'client_detail',
    'client_edit',
    'client_add_dog',
    'dog_delete',
]