"""Job application API: apply to jobs, list user applications, list applicants (employer)."""

from django.db import IntegrityError
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .breneo_user import external_user_id_from_request
from .models import CompanyStaffMembership, Job, JobApplication
from .permissions import CanViewJobApplicants
from .serializers import JobApplicationSerializer, JobApplicantSerializer


def _require_user_id(request) -> tuple[str | None, Response | None]:
    uid = external_user_id_from_request(request)
    if not uid:
        return None, Response(
            {
                "error": "user_id required",
                "message": (
                    "Provide external_user_id, user_id, or staff_user_id "
                    "in query or request body (Breneo user id)."
                ),
            },
            status=status.HTTP_400_BAD_REQUEST,
        )
    return uid, None


def _job_or_404(job_id: int) -> Job | Response:
    job = Job.objects.filter(pk=job_id).select_related("company").first()
    if not job:
        return Response({"error": "Job not found"}, status=status.HTTP_404_NOT_FOUND)
    return job


class JobApplyView(APIView):
    """
    POST /api/jobs/<job_id>/apply
    Create an application for the current breneo user.
    """

    authentication_classes = []
    permission_classes = []

    def post(self, request, job_id: int):
        uid, err = _require_user_id(request)
        if err:
            return err

        job = _job_or_404(job_id)
        if isinstance(job, Response):
            return job
        if not job.is_active:
            return Response(
                {"error": "Job is not accepting applications"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if JobApplication.objects.filter(external_user_id=uid, job=job).exists():
            return Response(
                {
                    "error": "Already applied",
                    "message": "You have already applied to this job.",
                },
                status=status.HTTP_409_CONFLICT,
            )

        now = timezone.now()
        try:
            application = JobApplication.objects.create(
                external_user_id=uid,
                job=job,
                applied_at=now,
                status="applied",
            )
        except IntegrityError:
            return Response(
                {
                    "error": "Already applied",
                    "message": "You have already applied to this job.",
                },
                status=status.HTTP_409_CONFLICT,
            )

        return Response(
            JobApplicationSerializer(application).data,
            status=status.HTTP_201_CREATED,
        )


class UserApplicationsView(APIView):
    """
    GET /api/users/me/applications
    List applications for the current breneo user.
    """

    authentication_classes = []
    permission_classes = []

    def get(self, request):
        uid, err = _require_user_id(request)
        if err:
            return err

        qs = (
            JobApplication.objects.filter(external_user_id=uid)
            .select_related("job", "job__company")
            .order_by("-applied_at", "-id")
        )
        return Response(JobApplicationSerializer(qs, many=True).data)


class JobApplicantsView(APIView):
    """
    GET /api/jobs/<job_id>/applicants
    Employer/recruiter: list applicants for a job (requires employer auth).
    """

    authentication_classes = []
    permission_classes = [CanViewJobApplicants]

    def get(self, request, job_id: int):
        job = _job_or_404(job_id)
        if isinstance(job, Response):
            return job

        if not self._staff_access(request, job):
            return Response(
                {"error": "Forbidden", "message": "Not authorized for this company's jobs."},
                status=status.HTTP_403_FORBIDDEN,
            )

        qs = (
            JobApplication.objects.filter(job=job)
            .select_related("job", "job__company")
            .order_by("-applied_at", "-id")
        )
        return Response(JobApplicantSerializer(qs, many=True).data)

    def _staff_access(self, request, job: Job) -> bool:
        """When external user id is sent, require staff on the job's company."""
        uid = external_user_id_from_request(request)
        if not uid:
            return True
        return CompanyStaffMembership.objects.filter(
            company=job.company,
            external_user_id=uid,
        ).exists()
