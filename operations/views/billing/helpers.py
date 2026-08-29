from operations.services.statements import get_unbilled_summary_for_client as _unbilled_summary


def get_unbilled_summary_for_client(client_id):
    """Completed visits not yet present on any statement line item for this dog."""
    return _unbilled_summary(client_id)
