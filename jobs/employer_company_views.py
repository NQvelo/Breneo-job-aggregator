"""Employer-facing company + industry API (synced with breneo-api user ids)."""

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Company, Industry
from .permissions import CanPostEmployerJob
from .serializers import CompanyDetailSerializer, EmployerCompanyWriteSerializer, IndustrySerializer


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


def _staff_scoped_access(request, company: Company) -> bool:
    """
    If ?staff_user_id= is sent, require that id in company.staff_user_ids.
    If omitted, allow (server-to-server with X-Employer-Key only).
    """
    sid = request.query_params.get("staff_user_id", "").strip()
    if not sid:
        return True
    return sid in (company.staff_user_ids or [])


class EmployerCompanyListCreateView(APIView):
    """
    GET  /api/employer/companies?staff_user_id=<breneo_user_id>  — companies that list this user in staff_user_ids
    POST /api/employer/companies — create company
    """

    authentication_classes = []
    permission_classes = [CanPostEmployerJob]

    def get(self, request):
        qs = Company.objects.prefetch_related("industries").order_by("name")
        staff_user_id = request.query_params.get("staff_user_id", "").strip()
        if staff_user_id:
            qs = qs.filter(staff_user_ids__contains=[staff_user_id])
        return Response(CompanyDetailSerializer(qs, many=True).data)

    def post(self, request):
        ser = EmployerCompanyWriteSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        company = ser.save()
        out = CompanyDetailSerializer(company).data
        return Response(out, status=status.HTTP_201_CREATED)


class EmployerCompanyDetailView(APIView):
    """
    GET   /api/employer/companies/<company_id>
    PATCH /api/employer/companies/<company_id>
    Optional: ?staff_user_id= for access check against staff_user_ids.
    """

    authentication_classes = []
    permission_classes = [CanPostEmployerJob]

    def get(self, request, company_id: int):
        try:
            company = Company.objects.prefetch_related("industries").get(pk=company_id)
        except Company.DoesNotExist:
            return Response({"error": "Company not found"}, status=status.HTTP_404_NOT_FOUND)
        if not _staff_scoped_access(request, company):
            return Response({"error": "Company not found"}, status=status.HTTP_404_NOT_FOUND)
        return Response(CompanyDetailSerializer(company).data)

    def patch(self, request, company_id: int):
        try:
            company = Company.objects.prefetch_related("industries").get(pk=company_id)
        except Company.DoesNotExist:
            return Response({"error": "Company not found"}, status=status.HTTP_404_NOT_FOUND)
        if not _staff_scoped_access(request, company):
            return Response({"error": "Company not found"}, status=status.HTTP_404_NOT_FOUND)

        ser = EmployerCompanyWriteSerializer(company, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        updated = ser.save()
        return Response(CompanyDetailSerializer(updated).data)

