"""Resolve breneo-api user fields from API requests (query, body, aliases)."""


def _field_from_mapping(data, keys: tuple[str, ...]) -> str:
    if not data or not hasattr(data, "get"):
        return ""
    for key in keys:
        val = data.get(key)
        if val is not None and str(val).strip():
            return str(val).strip()
    return ""


def external_user_field_from_request(request, *keys: str) -> str:
    """Read a string field from query params then JSON/body."""
    qp = getattr(request, "query_params", None) or {}
    val = _field_from_mapping(qp, keys)
    if val:
        return val
    data = getattr(request, "data", None)
    return _field_from_mapping(data, keys)


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
