from django.urls import path
from .views import (
    JobsGroupedByCompany,
    JobSearchView,
    JobDetailsView,
    CompanyDetailView,
    EmployerJobCreateView,
    EmployerJobDetailView,
    TriggerFetchView,
)
from .employer_company_views import (
    IndustryListView,
    EmployerCompanyListCreateView,
    EmployerCompanyDetailView,
)

urlpatterns = [
    path('', JobsGroupedByCompany.as_view(), name='jobs_grouped_by_company'),  # /api/ will point here
    path('search', JobSearchView.as_view(), name='job_search'),  # /api/search
    path('job-details', JobDetailsView.as_view(), name='job_details'),  # /api/job-details
    path('industries/', IndustryListView.as_view(), name='industry_list'),
    path('companies/<str:company_name>', CompanyDetailView.as_view(), name='company_detail'),  # /api/companies/Airbnb
    path('companies', CompanyDetailView.as_view(), name='company_detail_query'),  # /api/companies?name=Airbnb
    path('employer/companies', EmployerCompanyListCreateView.as_view(), name='employer_company_list_create'),
    path('employer/companies/<int:company_id>', EmployerCompanyDetailView.as_view(), name='employer_company_detail'),
    path('employer/jobs', EmployerJobCreateView.as_view(), name='employer_job_create'),
    path('employer/jobs/<int:job_id>', EmployerJobDetailView.as_view(), name='employer_job_detail'),
    path('trigger-fetch', TriggerFetchView.as_view(), name='trigger_fetch'),  # /api/trigger-fetch (for external cron)
]
