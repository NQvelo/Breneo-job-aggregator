import os

from rest_framework.permissions import BasePermission


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
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.groups.filter(name="Employer").exists()
        )
