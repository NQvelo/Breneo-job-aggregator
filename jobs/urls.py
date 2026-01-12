from django.urls import path
from .views import JobsGroupedByCompany, JobSearchView, JobDetailsView, CompanyDetailView

urlpatterns = [
    path('', JobsGroupedByCompany.as_view(), name='jobs_grouped_by_company'),  # /api/ will point here
    path('search', JobSearchView.as_view(), name='job_search'),  # /api/search
    path('job-details', JobDetailsView.as_view(), name='job_details'),  # /api/job-details
    path('companies/<str:company_name>', CompanyDetailView.as_view(), name='company_detail'),  # /api/companies/Airbnb
    path('companies', CompanyDetailView.as_view(), name='company_detail_query'),  # /api/companies?name=Airbnb
]
