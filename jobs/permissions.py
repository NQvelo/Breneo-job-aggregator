import os

from rest_framework.exceptions import NotAuthenticated
from rest_framework.permissions import BasePermission

from jobs.authentication.application_auth import ApplicationUser


class IsApplicationUserAuthenticated(BasePermission):
    """Require signed application headers or BFF X-Application-Key + external_user_id."""

    message = (
        "Application auth required. Send X-Breneo-User-Id, X-Breneo-Timestamp, "
        "and X-Breneo-Signature from breneo login response."
    )

    def has_permission(self, request, view):
        if not isinstance(getattr(request, "user", None), ApplicationUser):
            raise NotAuthenticated(detail=self.message)
        return True


class CanViewJobApplicants(BasePermission):
    """
    List job applicants if:
    - Header X-Employer-Key matches EMPLOYER_POST_SECRET (when set), OR
    - User is authenticated and in the Django group "Employer".
    """

    def has_permission(self, request, view):
        secret = os.environ.get("EMPLOYER_POST_SECRET", "").strip()
        if secret:
            if request.headers.get("X-Employer-Key") == secret:
                return True
        django_user = getattr(getattr(request, "_request", request), "user", None)
        return bool(
            django_user
            and django_user.is_authenticated
            and django_user.groups.filter(name="Employer").exists()
        )


class CanPostEmployerJob(BasePermission):
    """
    Allow posting if:
    - Header X-Employer-Key matches EMPLOYER_POST_SECRET (when set), OR
    - User is authenticated and in the Django group "Employer".
    """

    def has_permission(self, request, view):
        secret = os.environ.get("EMPLOYER_POST_SECRET", "").strip()
        if secret:
            if request.headers.get("X-Employer-Key") == secret:
                return True
        # Django session user lives on the underlying WSGI request (middleware), not on
        # DRF's request.user when authentication_classes is empty on the view.
        django_user = getattr(getattr(request, "_request", request), "user", None)
        return bool(
            django_user
            and django_user.is_authenticated
            and django_user.groups.filter(name="Employer").exists()
        )
