"""API plumbing shared by every app: error format, permissions, small helpers."""

from rest_framework import permissions
from rest_framework.exceptions import ValidationError
from rest_framework.views import exception_handler as drf_exception_handler

HOST_ROLES = ("owner", "manager")
STAFF_ROLES = ("owner", "manager", "cleaner", "cook", "caretaker", "security", "driver")


def _first_message(detail):
    if isinstance(detail, list) and detail:
        return _first_message(detail[0])
    if isinstance(detail, dict) and detail:
        key, value = next(iter(detail.items()))
        msg = _first_message(value)
        return msg if key in ("non_field_errors", "detail", "error") else f"{key.replace('_', ' ').capitalize()}: {msg}"
    return str(detail)


def exception_handler(exc, context):
    """DRF errors always carry a human sentence in "error" (the UI shows it as-is)."""
    response = drf_exception_handler(exc, context)
    if response is not None:
        data = response.data
        if isinstance(data, dict) and "error" in data:
            return response
        message = _first_message(data)
        response.data = {"error": message, "details": data} if isinstance(exc, ValidationError) else {"error": message}
    return response


class IsHost(permissions.BasePermission):
    message = "Host access only."

    def has_permission(self, request, view):
        u = request.user
        return bool(u and u.is_authenticated and (u.is_superuser or getattr(u, "role", "") in HOST_ROLES))


class IsStaffMember(permissions.BasePermission):
    message = "Staff access only."

    def has_permission(self, request, view):
        u = request.user
        return bool(u and u.is_authenticated and (u.is_superuser or getattr(u, "role", "") in STAFF_ROLES))


class IsGuest(permissions.IsAuthenticated):
    message = "Please log in with your phone number."


def client_ip(request):
    fwd = request.META.get("HTTP_X_FORWARDED_FOR", "")
    return fwd.split(",")[0].strip() if fwd else request.META.get("REMOTE_ADDR", "")
