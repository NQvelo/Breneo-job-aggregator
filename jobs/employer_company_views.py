"""Employer-facing company + industry API (synced with breneo-api user ids)."""

from urllib.parse import unquote

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Company, CompanyStaffMembership, Industry
from .permissions import CanPostEmployerJob
from .serializers import (
    CompanyDetailSerializer,
    CompanyStaffMembershipSerializer,
    EmployerCompanyWriteSerializer,
    IndustrySerializer,
)


class IndustryListView(APIView):
    """
    List industries for registration / company forms (read-only).
    GET /api/industries/
    """

    authentication_classes = []
    permission_classes = []

    def get(self, request):
        qs = Industry.objects.all().order_by("name")
        return Response(IndustrySerializer(qs, many=True).data)


def _external_user_id_from_request(request) -> str:
    return (
        request.query_params.get("external_user_id", "").strip()
        or request.query_params.get("staff_user_id", "").strip()
    )


def _staff_scoped_access(request, company: Company) -> bool:
    """
    If ?staff_user_id= or ?external_user_id= is sent, require a CompanyStaffMembership row.
    If omitted, allow (server-to-server with X-Employer-Key only).
    """
    sid = _external_user_id_from_request(request)
    if not sid:
        return True
    return CompanyStaffMembership.objects.filter(company=company, external_user_id=sid).exists()


def _company_queryset_base():
    return Company.objects.prefetch_related(
        "industries",
        "staff_memberships",
    ).order_by("name")


def _company_from_path_segment(company_name: str) -> Company | None:
    """
    Resolve employer URL path segment to a Company. `name` is unique on the model.
    Path is URL-decoded (e.g. %20 → space). Match is case-insensitive.
    """
    raw = unquote((company_name or "").strip())
    if not raw:
        return None
    return Company.objects.filter(name__iexact=raw).first()


class EmployerStaffMembershipListCreateView(APIView):
    """
    List and create staff memberships (breneo user ↔ company).

    GET  /api/employer/staff-memberships?company_id=&external_user_id=
    POST /api/employer/staff-memberships  JSON {"company_id": 1, "external_user_id": "..."}
    """

    authentication_classes = []
    permission_classes = [CanPostEmployerJob]

    def get(self, request):
        qs = CompanyStaffMembership.objects.select_related("company").order_by("company_id", "id")
        cid = request.query_params.get("company_id", "").strip()
        if cid:
            try:
                qs = qs.filter(company_id=int(cid))
            except ValueError:
                return Response(
                    {"error": "company_id must be an integer"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        uid = request.query_params.get("external_user_id", "").strip()
        if not uid:
            uid = request.query_params.get("staff_user_id", "").strip()
        if uid:
            qs = qs.filter(external_user_id=uid)
        return Response(CompanyStaffMembershipSerializer(qs, many=True).data)

    def post(self, request):
        ser = CompanyStaffMembershipSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        row = ser.save()
        row = CompanyStaffMembership.objects.select_related("company").get(pk=row.pk)
        return Response(
            CompanyStaffMembershipSerializer(row).data,
            status=status.HTTP_201_CREATED,
        )


class EmployerStaffMembershipDetailView(APIView):
    """
    GET    /api/employer/staff-memberships/<membership_id>
    PATCH  /api/employer/staff-memberships/<membership_id>
    PUT    /api/employer/staff-memberships/<membership_id>
    DELETE /api/employer/staff-memberships/<membership_id>
    """

    authentication_classes = []
    permission_classes = [CanPostEmployerJob]

    def get(self, request, membership_id: int):
        try:
            row = CompanyStaffMembership.objects.select_related("company").get(pk=membership_id)
        except CompanyStaffMembership.DoesNotExist:
            return Response({"error": "Membership not found"}, status=status.HTTP_404_NOT_FOUND)
        return Response(CompanyStaffMembershipSerializer(row).data)

    def patch(self, request, membership_id: int):
        try:
            row = CompanyStaffMembership.objects.get(pk=membership_id)
        except CompanyStaffMembership.DoesNotExist:
            return Response({"error": "Membership not found"}, status=status.HTTP_404_NOT_FOUND)
        ser = CompanyStaffMembershipSerializer(row, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        ser.save()
        row = CompanyStaffMembership.objects.select_related("company").get(pk=row.pk)
        return Response(CompanyStaffMembershipSerializer(row).data)

    def put(self, request, membership_id: int):
        try:
            row = CompanyStaffMembership.objects.get(pk=membership_id)
        except CompanyStaffMembership.DoesNotExist:
            return Response({"error": "Membership not found"}, status=status.HTTP_404_NOT_FOUND)
        ser = CompanyStaffMembershipSerializer(row, data=request.data, partial=False)
        ser.is_valid(raise_exception=True)
        ser.save()
        row = CompanyStaffMembership.objects.select_related("company").get(pk=row.pk)
        return Response(CompanyStaffMembershipSerializer(row).data)

    def delete(self, request, membership_id: int):
        deleted, _ = CompanyStaffMembership.objects.filter(pk=membership_id).delete()
        if not deleted:
            return Response({"error": "Membership not found"}, status=status.HTTP_404_NOT_FOUND)
        return Response(status=status.HTTP_204_NO_CONTENT)


class EmployerCompanyForUserView(APIView):
    """
    Companies the given breneo user belongs to (for dashboards / context after login).

    GET /api/employer/companies/for-user?external_user_id=<breneo_user_id>
    Alias query param: staff_user_id
    """

    authentication_classes = []
    permission_classes = [CanPostEmployerJob]

    def get(self, request):
        uid = _external_user_id_from_request(request)
        if not uid:
            return Response(
                {"error": "external_user_id or staff_user_id query parameter is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        qs = (
            _company_queryset_base()
            .filter(staff_memberships__external_user_id=uid)
            .distinct()
        )
        return Response(CompanyDetailSerializer(qs, many=True).data)


class EmployerCompanyMemberView(APIView):
    """
    Convenience attach / detach by company + user (same rows as staff-memberships).

    POST   /api/employer/companies/<company_name>/members  JSON {"external_user_id": "..."}
    DELETE /api/employer/companies/<company_name>/members?external_user_id=...
    company_name: URL-encoded company name (unique). Response bodies still include company "id".
    Body key staff_user_id is accepted as an alias for external_user_id.
    """

    authentication_classes = []
    permission_classes = [CanPostEmployerJob]

    @staticmethod
    def _parse_external_user_id(data, query_params) -> tuple[str | None, Response | None]:
        uid = (data.get("external_user_id") or data.get("staff_user_id") or "").strip()
        if not uid:
            uid = (
                query_params.get("external_user_id", "").strip()
                or query_params.get("staff_user_id", "").strip()
            )
        if not uid:
            return None, Response(
                {"error": "external_user_id is required (body or query)"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return uid, None

    def post(self, request, company_name: str):
        company = _company_from_path_segment(company_name)
        if not company:
            return Response({"error": "Company not found"}, status=status.HTTP_404_NOT_FOUND)

        uid, err = self._parse_external_user_id(request.data, request.query_params)
        if err:
            return err

        _, created = CompanyStaffMembership.objects.get_or_create(
            company=company, external_user_id=uid
        )
        out = CompanyDetailSerializer(
            Company.objects.prefetch_related("industries", "staff_memberships").get(pk=company.pk)
        ).data
        return Response(out, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)

    def delete(self, request, company_name: str):
        company = _company_from_path_segment(company_name)
        if not company:
            return Response({"error": "Company not found"}, status=status.HTTP_404_NOT_FOUND)

        uid, err = self._parse_external_user_id(request.data, request.query_params)
        if err:
            return err

        deleted, _ = CompanyStaffMembership.objects.filter(
            company=company, external_user_id=uid
        ).delete()
        if not deleted:
            return Response({"error": "Membership not found"}, status=status.HTTP_404_NOT_FOUND)
        return Response(status=status.HTTP_204_NO_CONTENT)


class EmployerCompanyListCreateView(APIView):
    """
    GET  /api/employer/companies — all companies (picker); optional ?search= (name icontains);
         ?external_user_id= or ?staff_user_id= — only companies that include this user
    POST /api/employer/companies — create company
    """

    authentication_classes = []
    permission_classes = [CanPostEmployerJob]

    def get(self, request):
        qs = _company_queryset_base()
        uid = _external_user_id_from_request(request)
        if uid:
            qs = qs.filter(staff_memberships__external_user_id=uid).distinct()
        search = request.query_params.get("search", "").strip()
        if search:
            qs = qs.filter(name__icontains=search)
        return Response(CompanyDetailSerializer(qs, many=True).data)

    def post(self, request):
        ser = EmployerCompanyWriteSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        company = ser.save()
        company = Company.objects.prefetch_related("industries", "staff_memberships").get(
            pk=company.pk
        )
        out = CompanyDetailSerializer(company).data
        return Response(out, status=status.HTTP_201_CREATED)


class EmployerCompanyDetailView(APIView):
    """
    GET   /api/employer/companies/<company_name>
    PUT   /api/employer/companies/<company_name>  — full update (all writable fields)
    PATCH /api/employer/companies/<company_name>
    company_name: URL-encoded unique name (not numeric id). JSON still includes "id".
    Optional: ?staff_user_id= or ?external_user_id= for access check.
    """

    authentication_classes = []
    permission_classes = [CanPostEmployerJob]

    def _get_company(self, company_name: str) -> Company | None:
        c = _company_from_path_segment(company_name)
        if not c:
            return None
        return (
            Company.objects.prefetch_related("industries", "staff_memberships")
            .filter(pk=c.pk)
            .first()
        )

    def get(self, request, company_name: str):
        company = self._get_company(company_name)
        if not company:
            return Response({"error": "Company not found"}, status=status.HTTP_404_NOT_FOUND)
        if not _staff_scoped_access(request, company):
            return Response({"error": "Company not found"}, status=status.HTTP_404_NOT_FOUND)
        return Response(CompanyDetailSerializer(company).data)

    def put(self, request, company_name: str):
        company = self._get_company(company_name)
        if not company:
            return Response({"error": "Company not found"}, status=status.HTTP_404_NOT_FOUND)
        if not _staff_scoped_access(request, company):
            return Response({"error": "Company not found"}, status=status.HTTP_404_NOT_FOUND)

        ser = EmployerCompanyWriteSerializer(company, data=request.data, partial=False)
        ser.is_valid(raise_exception=True)
        updated = ser.save()
        updated = Company.objects.prefetch_related("industries", "staff_memberships").get(
            pk=updated.pk
        )
        return Response(CompanyDetailSerializer(updated).data)

    def patch(self, request, company_name: str):
        company = self._get_company(company_name)
        if not company:
            return Response({"error": "Company not found"}, status=status.HTTP_404_NOT_FOUND)
        if not _staff_scoped_access(request, company):
            return Response({"error": "Company not found"}, status=status.HTTP_404_NOT_FOUND)

        ser = EmployerCompanyWriteSerializer(company, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        updated = ser.save()
        updated = Company.objects.prefetch_related("industries", "staff_memberships").get(
            pk=updated.pk
        )
        return Response(CompanyDetailSerializer(updated).data)
