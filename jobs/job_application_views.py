"""Job application REST API (apply, list, withdraw, recruiter applicants)."""

from __future__ import annotations

import logging

from drf_spectacular.utils import OpenApiParameter, extend_schema, inline_serializer
from rest_framework import serializers as drf_serializers, status
from rest_framework.exceptions import AuthenticationFailed, NotAuthenticated, PermissionDenied
from rest_framework.views import APIView

from .api_response import error_response, success_response
from .application_exceptions import JobApplicationError
from .applicant_profile import resolve_applicant_profile
from .authentication import ApplicationBFFRequiredAuthentication, get_application_user_id
from .breneo_user import external_user_id_from_request
from .pagination import ApplicationPagination
from .permissions import CanViewJobApplicants, IsApplicationUserAuthenticated
from .serializers import JobApplicantSerializer, JobApplicationSerializer
from .services.job_applications import JobApplicationService

logger = logging.getLogger(__name__)

APPLICATION_SORT_PARAMS = [
    OpenApiParameter(
        name="sort",
        type=str,
        location=OpenApiParameter.QUERY,
        description="Sort field: applied_at, -applied_at, created_at, -created_at, status, -status",
    ),
    OpenApiParameter(
        name="limit",
        type=int,
        location=OpenApiParameter.QUERY,
        description="Page size (default 20, max 100)",
    ),
    OpenApiParameter(
        name="page",
        type=int,
        location=OpenApiParameter.QUERY,
        description="Page number",
    ),
]

APPLICATION_BFF_PARAMS = [
    OpenApiParameter(
        name="X-Application-Key",
        type=str,
        location=OpenApiParameter.HEADER,
        required=True,
        description="Server secret (APPLICATION_API_SECRET). BFF only — never in browser.",
    ),
    OpenApiParameter(
        name="external_user_id",
        type=str,
        location=OpenApiParameter.QUERY,
        required=False,
        description="Breneo user id (query, body, or X-Breneo-User-Id header)",
    ),
]

_envelope = inline_serializer(
    name="ApplicationSuccessEnvelope",
    fields={
        "success": drf_serializers.BooleanField(),
        "message": drf_serializers.CharField(),
        "data": drf_serializers.JSONField(),
    },
)


class JobApplicationBaseView(APIView):
    service_class = JobApplicationService
    pagination_class = ApplicationPagination

    def get_service(self) -> JobApplicationService:
        return self.service_class()

    def get_paginator(self):
        return self.pagination_class()

    def paginate_queryset(self, request, queryset):
        paginator = self.get_paginator()
        page = paginator.paginate_queryset(queryset, request, view=self)
        return paginator, page

    def _sort_param(self, request) -> str:
        sort = (request.query_params.get("sort") or "-applied_at").strip()
        allowed = JobApplicationService().repo.SORT_FIELDS
        return sort if sort in allowed else "-applied_at"

    def handle_exception(self, exc):
        if isinstance(exc, (AuthenticationFailed, NotAuthenticated)):
            detail = exc.detail
            if isinstance(detail, list):
                message = "; ".join(str(d) for d in detail)
            else:
                message = str(detail)
            return error_response(
                message,
                status_code=status.HTTP_401_UNAUTHORIZED,
                error="not_authenticated",
            )
        if isinstance(exc, PermissionDenied):
            detail = exc.detail
            message = str(detail) if not isinstance(detail, list) else "; ".join(str(d) for d in detail)
            return error_response(
                message,
                status_code=status.HTTP_403_FORBIDDEN,
                error="forbidden",
            )
        if isinstance(exc, JobApplicationError):
            return error_response(
                exc.message,
                status_code=exc.status_code,
                error=exc.error_code,
                details=exc.details,
            )
        response = super().handle_exception(exc)
        if response is not None and hasattr(response, "data"):
            if isinstance(response.data, dict) and "success" not in response.data:
                message = response.data.get("message") or response.data.get("detail") or "Request failed"
                return error_response(
                    str(message),
                    status_code=response.status_code,
                    error=response.data.get("error"),
                    details=response.data.get("details"),
                )
        return response


class JobApplyView(JobApplicationBaseView):
    """
    POST /api/jobs/<job_id>/apply
    In-app apply for Breneo employer-posted jobs only (platform=employer).
    """

    authentication_classes = [ApplicationBFFRequiredAuthentication]
    permission_classes = [IsApplicationUserAuthenticated]

    @extend_schema(
        tags=["Job applications"],
        summary="Apply to a Breneo employer job",
        description=(
            "BFF/server only: X-Application-Key + external_user_id. "
            "Only jobs with platform=employer. Fetched ATS jobs use apply_url."
        ),
        parameters=APPLICATION_BFF_PARAMS,
        responses={201: _envelope, 400: _envelope, 401: _envelope, 404: _envelope, 409: _envelope},
    )
    def post(self, request, job_id: int):
        profile = resolve_applicant_profile(request)
        if get_application_user_id(request):
            profile.user_id = get_application_user_id(request)
        try:
            application = self.get_service().apply(profile, job_id)
        except JobApplicationError as exc:
            return error_response(
                exc.message,
                status_code=exc.status_code,
                error=exc.error_code,
                details=exc.details,
            )
        return success_response(
            JobApplicationSerializer(application, context={"request": request}).data,
            message="Application submitted successfully",
            status_code=status.HTTP_201_CREATED,
        )


class JobWithdrawApplicationView(JobApplicationBaseView):
    """DELETE /api/jobs/<job_id>/application — withdraw in-app application."""

    authentication_classes = [ApplicationBFFRequiredAuthentication]
    permission_classes = [IsApplicationUserAuthenticated]

    @extend_schema(
        tags=["Job applications"],
        summary="Withdraw application",
        parameters=APPLICATION_BFF_PARAMS,
        responses={200: _envelope, 401: _envelope, 404: _envelope},
    )
    def delete(self, request, job_id: int):
        user_id = get_application_user_id(request)
        try:
            application = self.get_service().withdraw(user_id, job_id)
        except JobApplicationError as exc:
            return error_response(
                exc.message,
                status_code=exc.status_code,
                error=exc.error_code,
                details=exc.details,
            )
        return success_response(
            JobApplicationSerializer(application, context={"request": request}).data,
            message="Application withdrawn successfully",
        )


class UserApplicationsView(JobApplicationBaseView):
    """GET /api/users/me/applications — list user's in-app applications."""

    authentication_classes = [ApplicationBFFRequiredAuthentication]
    permission_classes = [IsApplicationUserAuthenticated]

    @extend_schema(
        tags=["Job applications"],
        summary="List my applications",
        parameters=APPLICATION_SORT_PARAMS + APPLICATION_BFF_PARAMS,
        responses={200: _envelope, 401: _envelope},
    )
    def get(self, request):
        user_id = get_application_user_id(request)
        qs = self.get_service().list_user_applications(user_id, sort=self._sort_param(request))
        paginator, page = self.paginate_queryset(request, qs)
        if page is not None:
            data = JobApplicationSerializer(
                page, many=True, context={"request": request}
            ).data
            return paginator.build_response(
                data,
                message="Applications retrieved successfully",
            )
        data = JobApplicationSerializer(qs, many=True, context={"request": request}).data
        return success_response(
            {"items": data, "pagination": None},
            message="Applications retrieved successfully",
        )


class JobApplicantsView(JobApplicationBaseView):
    """GET /api/jobs/<job_id>/applicants — recruiter (X-Employer-Key)."""

    authentication_classes = []
    permission_classes = [CanViewJobApplicants]

    @extend_schema(
        tags=["Job applications"],
        summary="List job applicants (recruiter)",
        parameters=APPLICATION_SORT_PARAMS
        + [
            OpenApiParameter(
                name="external_user_id",
                type=str,
                location=OpenApiParameter.QUERY,
                required=False,
            ),
        ],
        responses={200: _envelope, 403: _envelope, 404: _envelope},
    )
    def get(self, request, job_id: int):
        scoped_uid = external_user_id_from_request(request) or get_application_user_id(request)
        try:
            applications, profiles, job = self.get_service().list_job_applicants(
                job_id,
                requester_user_id=scoped_uid or None,
                sort=self._sort_param(request),
                auth_token=None,
            )
        except JobApplicationError as exc:
            return error_response(
                exc.message,
                status_code=exc.status_code,
                error=exc.error_code,
                details=exc.details,
            )

        paginator, page = self.paginate_queryset(request, applications)
        serializer_ctx = {"request": request, "user_profiles": profiles}
        if page is not None:
            data = JobApplicantSerializer(page, many=True, context=serializer_ctx).data
            response = paginator.build_response(
                data,
                message="Applicants retrieved successfully",
            )
        else:
            data = JobApplicantSerializer(applications, many=True, context=serializer_ctx).data
            response = success_response(
                {"items": data, "pagination": None},
                message="Applicants retrieved successfully",
            )
        if isinstance(response.data.get("data"), dict):
            response.data["data"]["job"] = {
                "id": job.id,
                "title": job.title,
                "company_id": job.company_id,
                "company_name": job.company.name if job.company_id else None,
            }
        return response
