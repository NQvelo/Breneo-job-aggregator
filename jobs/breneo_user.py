"""Resolve breneo-api user id from API requests (query, body, aliases)."""


def external_user_id_from_request(request) -> str:
    """
    Breneo user id as string. Checks query then JSON/body.

    Accepted keys: external_user_id, staff_user_id, user_id.
    """
    qp = getattr(request, "query_params", None) or {}
    for key in ("external_user_id", "staff_user_id", "user_id"):
        val = (qp.get(key) or "").strip()
        if val:
            return val

    data = getattr(request, "data", None)
    if data and hasattr(data, "get"):
        for key in ("external_user_id", "staff_user_id", "user_id"):
            val = (data.get(key) or "").strip()
            if val:
                return val
    return ""
