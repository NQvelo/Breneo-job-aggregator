"""CRUD API for job_applicant_cv_views (employer + applicant)."""

from __future__ import annotations

from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status

from .api_response import error_response, success_response
from .application_exceptions import JobApplicationError
from .authentication import ApplicationBFFRequiredAuthentication, get_application_user_id
from .breneo_user import external_user_id_from_request
from .job_application_views import (
    APPLICATION_BFF_PARAMS,
    JobApplicationBaseView,
    _envelope,
)
from .permissions import CanViewJobApplicants, IsApplicationUserAuthenticated
from .serializers_cv_views import (
    ApplicantCvViewUpdateSerializer,
    EmployerCvViewUpdateSerializer,
    EmployerCvViewWriteSerializer,
    JobApplicantCvViewSerializer,
)


class EmployerJobCvViewListCreateView(JobApplicationBaseView):
    """
    GET  /api/jobs/<job_id>/applicant-cv-views
    POST /api/jobs/<job_id>/applicant-cv-views
    """

    authentication_classes = []
    permission_classes = [CanViewJobApplicants]

    @extend_schema(
        tags=["CV views"],
        summary="List CV view records for a job (employer)",
        parameters=[
            OpenApiParameter(name="external_user_id", type=str, location=OpenApiParameter.QUERY),
        ],
        responses={200: _envelope, 403: _envelope, 404: _envelope},
    )
    def get(self, request, job_id: int):
        requester = external_user_id_from_request(request) or ""
        try:
            rows = self.get_cv_view_service().list_for_job(job_id, requester_user_id=requester)
        except JobApplicationError as exc:
            return error_response(
                exc.message,
                status_code=exc.status_code,
                error=exc.error_code,
                details=exc.details,
            )
        return success_response(
            JobApplicantCvViewSerializer(rows, many=True).data,
            message="CV view records retrieved",
        )

    @extend_schema(
        tags=["CV views"],
        summary="Create CV view record (employer)",
        parameters=[
            OpenApiParameter(name="external_user_id", type=str, location=OpenApiParameter.QUERY),
        ],
        responses={201: _envelope, 403: _envelope, 404: _envelope, 409: _envelope},
    )
    def post(self, request, job_id: int):
        ser = EmployerCvViewWriteSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data
        requester = external_user_id_from_request(request) or ""
        viewer_user_id = data.get("viewer_user_id") or requester
        try:
            row = self.get_cv_view_service().create_cv_view(
                job_id,
                applicant_user_id=data["applicant_user_id"],
                viewer_user_id=viewer_user_id,
                requester_user_id=requester,
                view_count=data.get("view_count") or 1,
                first_viewed_at=data.get("first_viewed_at"),
                last_viewed_at=data.get("last_viewed_at"),
            )
        except JobApplicationError as exc:
            return error_response(
                exc.message,
                status_code=exc.status_code,
                error=exc.error_code,
                details=exc.details,
            )
        return success_response(
            JobApplicantCvViewSerializer(row).data,
            message="CV view record created",
            status_code=status.HTTP_201_CREATED,
        )


class EmployerJobCvViewDetailView(JobApplicationBaseView):
    """
    GET    /api/jobs/<job_id>/applicant-cv-views/<cv_view_id>
    PATCH  /api/jobs/<job_id>/applicant-cv-views/<cv_view_id>
    DELETE /api/jobs/<job_id>/applicant-cv-views/<cv_view_id>
    """

    authentication_classes = []
    permission_classes = [CanViewJobApplicants]

    def _requester(self, request) -> str:
        return external_user_id_from_request(request) or ""

    @extend_schema(tags=["CV views"], summary="Get CV view record (employer)")
    def get(self, request, job_id: int, cv_view_id: int):
        try:
            row = self.get_cv_view_service().get_for_employer(
                job_id,
                cv_view_id,
                requester_user_id=self._requester(request),
            )
        except JobApplicationError as exc:
            return error_response(
                exc.message,
                status_code=exc.status_code,
                error=exc.error_code,
                details=exc.details,
            )
        return success_response(
            JobApplicantCvViewSerializer(row).data,
            message="CV view record retrieved",
        )

    @extend_schema(tags=["CV views"], summary="Update CV view record (employer)")
    def patch(self, request, job_id: int, cv_view_id: int):
        ser = EmployerCvViewUpdateSerializer(data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        try:
            row = self.get_cv_view_service().update_cv_view_employer(
                job_id,
                cv_view_id,
                requester_user_id=self._requester(request),
                **ser.validated_data,
            )
        except JobApplicationError as exc:
            return error_response(
                exc.message,
                status_code=exc.status_code,
                error=exc.error_code,
                details=exc.details,
            )
        return success_response(
            JobApplicantCvViewSerializer(row).data,
            message="CV view record updated",
        )

    @extend_schema(tags=["CV views"], summary="Delete CV view record (employer)")
    def delete(self, request, job_id: int, cv_view_id: int):
        try:
            self.get_cv_view_service().delete_cv_view(
                job_id,
                cv_view_id,
                requester_user_id=self._requester(request),
            )
        except JobApplicationError as exc:
            return error_response(
                exc.message,
                status_code=exc.status_code,
                error=exc.error_code,
                details=exc.details,
            )
        return success_response(None, message="CV view record deleted")


class UserCvViewListView(JobApplicationBaseView):
    """GET /api/users/me/cv-views — applicant's CV view notifications."""

    authentication_classes = [ApplicationBFFRequiredAuthentication]
    permission_classes = [IsApplicationUserAuthenticated]

    @extend_schema(
        tags=["CV views"],
        summary="List my CV view records (applicant)",
        parameters=APPLICATION_BFF_PARAMS,
        responses={200: _envelope, 401: _envelope},
    )
    def get(self, request):
        user_id = get_application_user_id(request)
        rows = self.get_cv_view_service().list_for_applicant(user_id)
        return success_response(
            JobApplicantCvViewSerializer(rows, many=True).data,
            message="CV view records retrieved",
        )


class UserCvViewDetailView(JobApplicationBaseView):
    """
    GET   /api/users/me/cv-views/<cv_view_id>
    PATCH /api/users/me/cv-views/<cv_view_id>
    """

    authentication_classes = [ApplicationBFFRequiredAuthentication]
    permission_classes = [IsApplicationUserAuthenticated]

    @extend_schema(
        tags=["CV views"],
        summary="Get CV view record (applicant)",
        parameters=APPLICATION_BFF_PARAMS,
    )
    def get(self, request, cv_view_id: int):
        user_id = get_application_user_id(request)
        try:
            row = self.get_cv_view_service().get_for_applicant(
                cv_view_id,
                applicant_user_id=user_id,
            )
        except JobApplicationError as exc:
            return error_response(
                exc.message,
                status_code=exc.status_code,
                error=exc.error_code,
                details=exc.details,
            )
        return success_response(
            JobApplicantCvViewSerializer(row).data,
            message="CV view record retrieved",
        )

    @extend_schema(
        tags=["CV views"],
        summary="Acknowledge CV view (applicant)",
        parameters=APPLICATION_BFF_PARAMS,
    )
    def patch(self, request, cv_view_id: int):
        ser = ApplicantCvViewUpdateSerializer(data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        user_id = get_application_user_id(request)
        try:
            row = self.get_cv_view_service().update_cv_view_applicant(
                cv_view_id,
                applicant_user_id=user_id,
                **ser.validated_data,
            )
        except JobApplicationError as exc:
            return error_response(
                exc.message,
                status_code=exc.status_code,
                error=exc.error_code,
                details=exc.details,
            )
        return success_response(
            JobApplicantCvViewSerializer(row).data,
            message="CV view record updated",
        )
