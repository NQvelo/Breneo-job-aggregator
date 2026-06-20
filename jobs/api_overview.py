"""
Machine-readable list of public API routes for GET /api/overview/
"""

from django.http import JsonResponse
from django.views import View


AUTH_MODES = {
    "public": "No auth required.",
    "employer": (
        "Header X-Employer-Key = EMPLOYER_POST_SECRET, or Django session in group Employer. "
        "Optional ?external_user_id= / staff_user_id for scoped staff access."
    ),
    "application_bff": (
        "Header X-Application-Key = APPLICATION_API_SECRET (or EMPLOYER_POST_SECRET). "
        "User id via external_user_id (query/body) or X-Breneo-User-Id. BFF only — never browser."
    ),
}

RESPONSE_ENVELOPE = {
    "application_routes": {
        "success": True,
        "message": "Human-readable status",
        "data": "{ ... payload ... }",
    },
    "employer_json_routes": "Raw JSON array or object (no envelope) unless noted.",
    "errors": {
        "success": False,
        "message": "Error description",
        "error": "machine_code",
        "details": "optional object",
    },
}

CV_VIEW_WORKFLOW = {
    "table": "job_applicant_cv_views",
    "unique_key": "(job_id, applicant_user_id, viewer_user_id)",
    "fields": [
        "id",
        "job_id",
        "job_title",
        "company_id",
        "company_name",
        "application_id",
        "applicant_user_id",
        "viewer_user_id",
        "first_viewed_at",
        "last_viewed_at",
        "view_count",
        "applicant_acknowledged_at",
        "created_at",
        "updated_at",
    ],
    "steps": [
        {
            "order": 1,
            "actor": "applicant",
            "action": "Apply to job",
            "method": "POST",
            "path": "/api/jobs/{job_id}/apply",
            "auth": "application_bff",
        },
        {
            "order": 2,
            "actor": "employer",
            "action": "List applicants for job",
            "method": "GET",
            "path": "/api/jobs/{job_id}/applicants",
            "auth": "employer",
            "notes": "Response includes employer_viewed_cv and cv_viewed_by_me flags per applicant.",
        },
        {
            "order": 3,
            "actor": "employer",
            "action": "Open applicant CV page — record view",
            "method": "POST",
            "path": "/api/jobs/{job_id}/applicants/{applicant_user_id}/cv-view",
            "auth": "employer",
            "notes": "Creates row or increments view_count and updates last_viewed_at.",
        },
        {
            "order": 4,
            "actor": "applicant",
            "action": "See viewed status on my applications",
            "method": "GET",
            "path": "/api/users/me/applications",
            "auth": "application_bff",
            "notes": "Each item includes employer_viewed_cv, employer_first_viewed_at, employer_cv_view_count.",
        },
        {
            "order": 5,
            "actor": "applicant",
            "action": "List CV view notifications",
            "method": "GET",
            "path": "/api/users/me/cv-views",
            "auth": "application_bff",
        },
        {
            "order": 6,
            "actor": "applicant",
            "action": "Acknowledge / dismiss notification",
            "method": "PATCH",
            "path": "/api/users/me/cv-views/{cv_view_id}",
            "auth": "application_bff",
            "body_example": {"acknowledge": True},
        },
        {
            "order": 7,
            "actor": "employer",
            "action": "Admin CRUD on CV view rows",
            "method": "GET|POST|PATCH|DELETE",
            "path": "/api/jobs/{job_id}/applicant-cv-views[/{cv_view_id}]",
            "auth": "employer",
            "notes": "Manual create/edit/delete; use shortcut POST in step 3 for normal tracking.",
        },
    ],
}

API_GROUPS = [
    {
        "id": "meta",
        "title": "Meta & docs",
        "auth": "public",
        "endpoints": [
            {"methods": ["GET"], "path": "/health/", "description": "Liveness/health check (plain text ok)."},
            {
                "methods": ["GET"],
                "path": "/api/overview/",
                "description": "JSON index of all routes, auth modes, and CV view workflow.",
            },
            {"methods": ["GET"], "path": "/api/schema/", "description": "OpenAPI schema (drf-spectacular)."},
            {"methods": ["GET"], "path": "/api/docs/", "description": "Swagger UI."},
            {"methods": ["GET"], "path": "/api/redoc/", "description": "ReDoc."},
        ],
    },
    {
        "id": "jobs_public",
        "title": "Jobs (public / legacy)",
        "auth": "public",
        "endpoints": [
            {"methods": ["GET"], "path": "/api/", "description": "Active jobs grouped by company (legacy)."},
            {"methods": ["GET"], "path": "/api/search", "description": "Search and filter jobs."},
            {"methods": ["GET"], "path": "/api/job-details", "description": "Job detail by id or external reference."},
            {"methods": ["GET"], "path": "/api/v1/jobs/", "description": "Paginated job list (filters, search, sort)."},
            {"methods": ["GET"], "path": "/api/v1/jobs/{id}/", "description": "Single job by primary key."},
        ],
    },
    {
        "id": "companies_public",
        "title": "Companies & industries (public)",
        "auth": "public",
        "endpoints": [
            {"methods": ["GET"], "path": "/api/industries/", "description": "List industries (id, name)."},
            {"methods": ["GET"], "path": "/api/companies", "description": "Company detail by query ?name=."},
            {
                "methods": ["GET"],
                "path": "/api/companies/{company_name}",
                "description": "Company + jobs by company name (URL-encoded).",
            },
        ],
    },
    {
        "id": "applications",
        "title": "Job applications (applicant BFF)",
        "auth": "application_bff",
        "endpoints": [
            {
                "methods": ["POST"],
                "path": "/api/jobs/{job_id}/apply",
                "description": "Apply to employer job. Body: external_user_id + profile fields.",
            },
            {
                "methods": ["DELETE"],
                "path": "/api/jobs/{job_id}/application",
                "description": "Withdraw application.",
            },
            {
                "methods": ["GET"],
                "path": "/api/users/me/applications",
                "description": "List my applications with employer_viewed_cv summary fields.",
            },
            {
                "methods": ["GET"],
                "path": "/api/jobs/{job_id}/applicants",
                "auth": "employer",
                "description": "List applicants (recruiter) with CV view flags.",
            },
        ],
    },
    {
        "id": "cv_views",
        "title": "CV view tracking (employer + applicant)",
        "auth": "employer_or_application_bff",
        "workflow": CV_VIEW_WORKFLOW,
        "endpoints": [
            {
                "methods": ["POST"],
                "path": "/api/jobs/{job_id}/applicants/{applicant_user_id}/cv-view",
                "auth": "employer",
                "description": "Record/increment CV view when employer opens applicant profile.",
            },
            {
                "methods": ["GET", "POST"],
                "path": "/api/jobs/{job_id}/applicant-cv-views",
                "auth": "employer",
                "description": "List (GET) or manually create (POST) CV view rows for a job.",
            },
            {
                "methods": ["GET", "PATCH", "DELETE"],
                "path": "/api/jobs/{job_id}/applicant-cv-views/{cv_view_id}",
                "auth": "employer",
                "description": "Get, update, or delete one CV view row.",
            },
            {
                "methods": ["GET"],
                "path": "/api/users/me/cv-views",
                "auth": "application_bff",
                "description": "Applicant: list CV views on my profile.",
            },
            {
                "methods": ["GET", "PATCH"],
                "path": "/api/users/me/cv-views/{cv_view_id}",
                "auth": "application_bff",
                "description": "Applicant: get or acknowledge a CV view ({ acknowledge: true }).",
            },
        ],
    },
    {
        "id": "cron",
        "title": "Operations",
        "auth": "public",
        "endpoints": [
            {
                "methods": ["GET", "POST"],
                "path": "/api/trigger-fetch",
                "description": "Run fetch_jobs command (optional FETCH_SECRET).",
            },
        ],
    },
    {
        "id": "employer",
        "title": "Employer APIs",
        "auth": "employer",
        "endpoints": [
            {
                "methods": ["GET", "POST"],
                "path": "/api/employer/companies",
                "description": "List/create companies (?search=, ?external_user_id=).",
            },
            {
                "methods": ["GET"],
                "path": "/api/employer/companies/for-user",
                "description": "Companies for user (?external_user_id= required).",
            },
            {
                "methods": ["GET", "PUT", "PATCH", "DELETE"],
                "path": "/api/employer/companies/{company_id}",
                "description": "Company CRUD; DELETE removes logo only.",
            },
            {
                "methods": ["POST", "DELETE"],
                "path": "/api/employer/companies/{company_id}/members",
                "description": "Add/remove staff with status pending|member|admin.",
            },
            {
                "methods": ["GET", "POST"],
                "path": "/api/employer/staff-memberships",
                "description": "List/create staff memberships with profile + status.",
            },
            {
                "methods": ["GET", "PUT", "PATCH", "DELETE"],
                "path": "/api/employer/staff-memberships/{membership_id}",
                "description": "Membership CRUD; admin rules on DELETE/PATCH status.",
            },
            {
                "methods": ["POST"],
                "path": "/api/jobs/parse-description",
                "description": "Parse job description via Gemini into structured arrays.",
            },
            {
                "methods": ["GET", "POST"],
                "path": "/api/employer/jobs",
                "description": "List/create employer jobs (?company_id=).",
            },
            {
                "methods": ["GET", "POST", "PATCH", "DELETE"],
                "path": "/api/employer/jobs/{job_id}",
                "description": "Job CRUD; POST mirrors PATCH.",
            },
        ],
    },
]


class ApiOverviewView(View):
    """GET /api/overview/ — JSON catalog of routes."""

    def get(self, request):
        return JsonResponse(
            {
                "service": "job-aggregator",
                "documentation_html": "/",
                "auth_modes": AUTH_MODES,
                "response_envelope": RESPONSE_ENVELOPE,
                "cv_view_workflow": CV_VIEW_WORKFLOW,
                "groups": API_GROUPS,
            }
        )
