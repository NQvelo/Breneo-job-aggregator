from django.urls import path

from .api_overview import ApiOverviewView
from .views import (
    JobsGroupedByCompany,
    JobSearchView,
    JobDetailsView,
    CompanyDetailView,
    EmployerJobCreateView,
    EmployerJobDetailView,
    ParseJobDescriptionView,
    TriggerFetchView,
)
from .employer_company_views import (
    IndustryListView,
    EmployerCompanyForUserView,
    EmployerCompanyListCreateView,
    EmployerCompanyDetailView,
    EmployerCompanyMemberView,
    EmployerStaffMembershipListCreateView,
    EmployerStaffMembershipDetailView,
)
from .job_application_views import (
    JobApplyView,
    JobWithdrawApplicationView,
    UserApplicationsView,
    JobApplicantsView,
)

urlpatterns = [
    path('overview/', ApiOverviewView.as_view(), name='api_overview'),
    path('', JobsGroupedByCompany.as_view(), name='jobs_grouped_by_company'),  # /api/ will point here
    path('search', JobSearchView.as_view(), name='job_search'),  # /api/search
    path('job-details', JobDetailsView.as_view(), name='job_details'),  # /api/job-details
    path('industries/', IndustryListView.as_view(), name='industry_list'),
    path('companies/<str:company_name>', CompanyDetailView.as_view(), name='company_detail'),  # /api/companies/Airbnb
    path('companies', CompanyDetailView.as_view(), name='company_detail_query'),  # /api/companies?name=Airbnb
    path(
        'employer/staff-memberships',
        EmployerStaffMembershipListCreateView.as_view(),
        name='employer_staff_membership_list_create',
    ),
    path(
        'employer/staff-memberships/<int:membership_id>',
        EmployerStaffMembershipDetailView.as_view(),
        name='employer_staff_membership_detail',
    ),
    path('employer/companies/for-user', EmployerCompanyForUserView.as_view(), name='employer_company_for_user'),
    path(
        'employer/companies/<int:company_id>/members',
        EmployerCompanyMemberView.as_view(),
        name='employer_company_members',
    ),
    path('employer/companies', EmployerCompanyListCreateView.as_view(), name='employer_company_list_create'),
    path(
        'employer/companies/<int:company_id>',
        EmployerCompanyDetailView.as_view(),
        name='employer_company_detail',
    ),
    path('users/me/applications', UserApplicationsView.as_view(), name='user_applications'),
    path('jobs/<int:job_id>/apply', JobApplyView.as_view(), name='job_apply'),
    path('jobs/<int:job_id>/application', JobWithdrawApplicationView.as_view(), name='job_withdraw_application'),
    path('jobs/<int:job_id>/applicants', JobApplicantsView.as_view(), name='job_applicants'),
    path('jobs/parse-description', ParseJobDescriptionView.as_view(), name='parse_job_description'),
    path('employer/jobs', EmployerJobCreateView.as_view(), name='employer_job_create'),
    path('employer/jobs/<int:job_id>', EmployerJobDetailView.as_view(), name='employer_job_detail'),
    path('trigger-fetch', TriggerFetchView.as_view(), name='trigger_fetch'),  # /api/trigger-fetch (for external cron)
]
