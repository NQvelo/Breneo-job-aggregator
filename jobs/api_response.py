"""Standard JSON envelope for frontend-friendly API responses."""

from __future__ import annotations

from typing import Any

from rest_framework.response import Response


def success_response(
    data: Any = None,
    *,
    message: str = "OK",
    status_code: int = 200,
    meta: dict[str, Any] | None = None,
) -> Response:
    body: dict[str, Any] = {
        "success": True,
        "message": message,
        "data": data,
    }
    if meta:
        body["meta"] = meta
    return Response(body, status=status_code)


def error_response(
    message: str,
    *,
    status_code: int = 400,
    error: str | None = None,
    details: Any = None,
) -> Response:
    body: dict[str, Any] = {
        "success": False,
        "message": message,
        "data": None,
    }
    if error:
        body["error"] = error
    if details is not None:
        body["details"] = details
    return Response(body, status=status_code)
