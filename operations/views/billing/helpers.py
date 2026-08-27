from operations.models import AccountStatement


def get_unbilled_summary_for_client(client_id):
    """
    Calculates completed visits not yet associated with an AccountStatement.
    """
    # Query logic for draft/unbilled stay totals
    pass