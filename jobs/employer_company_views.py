"""Employer-facing company + industry API (synced with breneo-api user ids)."""

from django.http import QueryDict
from rest_framework import status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
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
from .services.staff_memberships import (
    delete_staff_membership,
    resolve_is_admin_on_create,
    staff_profile_create_kwargs,
)


def _employer_company_write_data(request):
    """
    Normalize multipart uploads so the image always reaches the serializer as logo_upload.

    Common frontend mistakes: file under logoUpload, file, image, or employer_logo instead of logo_upload.
    """
    files = getattr(request, "FILES", None)
    if not files or files.get("logo_upload"):
        return request.data
    for alt in ("logoUpload", "employer_logo", "file", "image"):
        if alt in files:
            raw = request.data
            if isinstance(raw, QueryDict):
                payload = raw.copy()
                payload.setlist("logo_upload", files.getlist(alt))
                return payload
            payload = dict(raw) if hasattr(raw, "keys") else {}
            payload["logo_upload"] = files.get(alt)
            return payload
    return request.data


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


def _employer_company_by_id(company_id: int) -> Company | None:
    return (
        Company.objects.prefetch_related("industries", "staff_memberships")
        .filter(pk=company_id)
        .first()
    )


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
        ser = CompanyStaffMembershipSerializer(
            data=request.data,
            context={"request": request},
        )
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
        ser = CompanyStaffMembershipSerializer(
            row,
            data=request.data,
            partial=True,
            context={"request": request},
        )
        ser.is_valid(raise_exception=True)
        ser.save()
        row = CompanyStaffMembership.objects.select_related("company").get(pk=row.pk)
        return Response(CompanyStaffMembershipSerializer(row).data)

    def put(self, request, membership_id: int):
        try:
            row = CompanyStaffMembership.objects.get(pk=membership_id)
        except CompanyStaffMembership.DoesNotExist:
            return Response({"error": "Membership not found"}, status=status.HTTP_404_NOT_FOUND)
        ser = CompanyStaffMembershipSerializer(
            row,
            data=request.data,
            partial=False,
            context={"request": request},
        )
        ser.is_valid(raise_exception=True)
        ser.save()
        row = CompanyStaffMembership.objects.select_related("company").get(pk=row.pk)
        return Response(CompanyStaffMembershipSerializer(row).data)

    def delete(self, request, membership_id: int):
        try:
            row = CompanyStaffMembership.objects.select_related("company").get(pk=membership_id)
        except CompanyStaffMembership.DoesNotExist:
            return Response({"error": "Membership not found"}, status=status.HTTP_404_NOT_FOUND)
        ok, err = delete_staff_membership(
            row,
            requester_user_id=_external_user_id_from_request(request),
        )
        if not ok:
            return Response({"error": err}, status=status.HTTP_403_FORBIDDEN)
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
        return Response(
            CompanyDetailSerializer(qs, many=True, context={"request": request}).data
        )


class EmployerCompanyMemberView(APIView):
    """
    Convenience attach / detach by company + user (same rows as staff-memberships).

    POST   /api/employer/companies/<company_id>/members  JSON {"external_user_id": "..."}
    DELETE /api/employer/companies/<company_id>/members?external_user_id=...
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

    def post(self, request, company_id: int):
        company = _employer_company_by_id(company_id)
        if not company:
            return Response({"error": "Company not found"}, status=status.HTTP_404_NOT_FOUND)

        uid, err = self._parse_external_user_id(request.data, request.query_params)
        if err:
            return err

        profile_kwargs = staff_profile_create_kwargs(request, uid)
        is_admin = resolve_is_admin_on_create(
            company,
            bool(request.data.get("is_admin")),
        )
        row, created = CompanyStaffMembership.objects.get_or_create(
            company=company,
            external_user_id=uid,
            defaults={**profile_kwargs, "is_admin": is_admin},
        )
        if not created and profile_kwargs:
            update_fields = []
            for field, value in profile_kwargs.items():
                if value and getattr(row, field) != value:
                    setattr(row, field, value)
                    update_fields.append(field)
            if update_fields:
                row.save(update_fields=update_fields)
        out = CompanyDetailSerializer(
            Company.objects.prefetch_related("industries", "staff_memberships").get(
                pk=company.pk
            ),
            context={"request": request},
        ).data
        return Response(out, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)

    def delete(self, request, company_id: int):
        company = _employer_company_by_id(company_id)
        if not company:
            return Response({"error": "Company not found"}, status=status.HTTP_404_NOT_FOUND)

        uid, err = self._parse_external_user_id(request.data, request.query_params)
        if err:
            return err

        try:
            row = CompanyStaffMembership.objects.get(company=company, external_user_id=uid)
        except CompanyStaffMembership.DoesNotExist:
            return Response({"error": "Membership not found"}, status=status.HTTP_404_NOT_FOUND)

        ok, err = delete_staff_membership(
            row,
            requester_user_id=_external_user_id_from_request(request),
        )
        if not ok:
            return Response({"error": err}, status=status.HTTP_403_FORBIDDEN)
        return Response(status=status.HTTP_204_NO_CONTENT)


class EmployerCompanyListCreateView(APIView):
    """
    GET  /api/employer/companies — all companies (picker); optional ?search= (name icontains);
         ?external_user_id= or ?staff_user_id= — only companies that include this user
    POST /api/employer/companies — create company
    """

    authentication_classes = []
    permission_classes = [CanPostEmployerJob]
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def get(self, request):
        qs = _company_queryset_base()
        uid = _external_user_id_from_request(request)
        if uid:
            qs = qs.filter(staff_memberships__external_user_id=uid).distinct()
        search = request.query_params.get("search", "").strip()
        if search:
            qs = qs.filter(name__icontains=search)
        return Response(
            CompanyDetailSerializer(qs, many=True, context={"request": request}).data
        )

    def post(self, request):
        ser = EmployerCompanyWriteSerializer(data=_employer_company_write_data(request))
        ser.is_valid(raise_exception=True)
        company = ser.save()
        company = Company.objects.prefetch_related("industries", "staff_memberships").get(
            pk=company.pk
        )
        out = CompanyDetailSerializer(
            company, context={"request": request}
        ).data
        return Response(out, status=status.HTTP_201_CREATED)


class EmployerCompanyDetailView(APIView):
    """
    GET   /api/employer/companies/<company_id>
    PUT   /api/employer/companies/<company_id>  — full update (all writable fields)
    PATCH /api/employer/companies/<company_id>
    Optional: ?staff_user_id= or ?external_user_id= for access check.
    """

    authentication_classes = []
    permission_classes = [CanPostEmployerJob]
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def get(self, request, company_id: int):
        company = _employer_company_by_id(company_id)
        if not company:
            return Response({"error": "Company not found"}, status=status.HTTP_404_NOT_FOUND)
        if not _staff_scoped_access(request, company):
            return Response({"error": "Company not found"}, status=status.HTTP_404_NOT_FOUND)
        return Response(
            CompanyDetailSerializer(company, context={"request": request}).data
        )

    def put(self, request, company_id: int):
        company = _employer_company_by_id(company_id)
        if not company:
            return Response({"error": "Company not found"}, status=status.HTTP_404_NOT_FOUND)
        if not _staff_scoped_access(request, company):
            return Response({"error": "Company not found"}, status=status.HTTP_404_NOT_FOUND)

        ser = EmployerCompanyWriteSerializer(
            company, data=_employer_company_write_data(request), partial=False
        )
        ser.is_valid(raise_exception=True)
        try:
            updated = ser.save()
        except Exception as exc:
            return Response(
                {"error": "Failed to save company profile image", "details": str(exc)},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        updated = Company.objects.prefetch_related("industries", "staff_memberships").get(
            pk=updated.pk
        )
        return Response(
            CompanyDetailSerializer(updated, context={"request": request}).data
        )

    def patch(self, request, company_id: int):
        company = _employer_company_by_id(company_id)
        if not company:
            return Response({"error": "Company not found"}, status=status.HTTP_404_NOT_FOUND)
        if not _staff_scoped_access(request, company):
            return Response({"error": "Company not found"}, status=status.HTTP_404_NOT_FOUND)

        ser = EmployerCompanyWriteSerializer(
            company, data=_employer_company_write_data(request), partial=True
        )
        ser.is_valid(raise_exception=True)
        try:
            updated = ser.save()
        except Exception as exc:
            return Response(
                {"error": "Failed to save company profile image", "details": str(exc)},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        updated = Company.objects.prefetch_related("industries", "staff_memberships").get(
            pk=updated.pk
        )
        return Response(
            CompanyDetailSerializer(updated, context={"request": request}).data
        )

    def delete(self, request, company_id: int):
        company = _employer_company_by_id(company_id)
        if not company:
            return Response({"error": "Company not found"}, status=status.HTTP_404_NOT_FOUND)
        if not _staff_scoped_access(request, company):
            return Response({"error": "Company not found"}, status=status.HTTP_404_NOT_FOUND)

        if not company.logo_upload:
            return Response(
                {"success": True, "message": "No uploaded logo to delete."},
                status=status.HTTP_200_OK,
            )
        try:
            company.logo_upload.delete(save=False)
            company.logo_upload = None
            company.save(update_fields=["logo_upload", "updated_at"])
        except Exception as exc:
            return Response(
                {"error": "Failed to delete company profile image", "details": str(exc)},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return Response(
            {"success": True, "message": "Company logo deleted."},
            status=status.HTTP_200_OK,
        )
