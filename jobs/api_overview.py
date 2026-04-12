"""
Machine-readable list of public API routes for GET /api/overview/
"""

from django.http import JsonResponse
from django.views import View


API_GROUPS = [
    {
        "id": "meta",
        "title": "Meta & docs",
        "endpoints": [
            {
                "methods": ["GET"],
                "path": "/health/",
                "description": "Liveness/health check (plain text ok).",
            },
            {
                "methods": ["GET"],
                "path": "/api/overview/",
                "description": "This JSON index of all routes.",
            },
            {
                "methods": ["GET"],
                "path": "/api/schema/",
                "description": "OpenAPI schema (drf-spectacular).",
            },
            {
                "methods": ["GET"],
                "path": "/api/docs/",
                "description": "Swagger UI.",
            },
            {
                "methods": ["GET"],
                "path": "/api/redoc/",
                "description": "ReDoc.",
            },
        ],
    },
    {
        "id": "jobs_public",
        "title": "Jobs (public / legacy)",
        "endpoints": [
            {
                "methods": ["GET"],
                "path": "/api/",
                "description": "Active jobs grouped by company (legacy).",
            },
            {
                "methods": ["GET"],
                "path": "/api/search",
                "description": "Search and filter jobs (query, filters, pagination).",
            },
            {
                "methods": ["GET"],
                "path": "/api/job-details",
                "description": "Job detail by id or external reference (see view for query params).",
            },
            {
                "methods": ["GET"],
                "path": "/api/v1/jobs/",
                "description": "Paginated job list (ViewSet; filters, search, sort).",
            },
            {
                "methods": ["GET"],
                "path": "/api/v1/jobs/{id}/",
                "description": "Single job by primary key.",
            },
        ],
    },
    {
        "id": "companies_public",
        "title": "Companies & industries (public)",
        "endpoints": [
            {
                "methods": ["GET"],
                "path": "/api/industries/",
                "description": "List industries (id, name).",
            },
            {
                "methods": ["GET"],
                "path": "/api/companies",
                "description": "Company detail by query ?name= (public job site).",
            },
            {
                "methods": ["GET"],
                "path": "/api/companies/{company_name}",
                "description": "Company + jobs by company name in path (URL-encoded).",
            },
        ],
    },
    {
        "id": "cron",
        "title": "Operations",
        "endpoints": [
            {
                "methods": ["GET", "POST"],
                "path": "/api/trigger-fetch",
                "description": "Run fetch_jobs command (optional FETCH_SECRET query/body).",
            },
        ],
    },
    {
        "id": "employer",
        "title": "Employer APIs (auth: X-Employer-Key = EMPLOYER_POST_SECRET, or Employer session)",
        "endpoints": [
            {
                "methods": ["GET", "POST"],
                "path": "/api/employer/companies",
                "description": "List companies (?search=, ?external_user_id=); POST create (JSON or multipart/form-data; file field logo_upload for logo image).",
            },
            {
                "methods": ["GET"],
                "path": "/api/employer/companies/for-user",
                "description": "Companies for a Breneo user (?external_user_id= required).",
            },
            {
                "methods": ["GET", "PUT", "PATCH", "DELETE"],
                "path": "/api/employer/companies/{company_id}",
                "description": "Company profile by id; optional ?external_user_id=. GET returns resolved logo URL in `logo` (includes uploaded file). PUT/PATCH: JSON or multipart with logo_upload=file. DELETE removes current uploaded logo.",
            },
            {
                "methods": ["POST", "DELETE"],
                "path": "/api/employer/companies/{company_id}/members",
                "description": "Add/remove staff by external_user_id (body or query).",
            },
            {
                "methods": ["GET", "POST"],
                "path": "/api/employer/staff-memberships",
                "description": "List (?company_id=, ?external_user_id=); POST create membership.",
            },
            {
                "methods": ["GET", "PUT", "PATCH", "DELETE"],
                "path": "/api/employer/staff-memberships/{membership_id}",
                "description": "Retrieve, update, or delete a membership row.",
            },
            {
                "methods": ["POST"],
                "path": "/api/jobs/parse-description",
                "description": "Gemini: parse job description text into responsibilities, qualifications, skills_required (JSON arrays; employer_manual only; same auth as employer APIs).",
            },
            {
                "methods": ["GET", "POST"],
                "path": "/api/employer/jobs",
                "description": "GET list (?company_id= or ?company=); POST create employer job.",
            },
            {
                "methods": ["GET", "POST", "PATCH", "DELETE"],
                "path": "/api/employer/jobs/{job_id}",
                "description": "GET/PATCH/POST update/DELETE job; optional ?company_id= scope.",
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
                "groups": API_GROUPS,
            }
        )
