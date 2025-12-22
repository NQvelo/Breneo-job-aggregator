from django.urls import path
from .views import JobsGroupedByCompany, JobSearchView

urlpatterns = [
    path('', JobsGroupedByCompany.as_view(), name='jobs_grouped_by_company'),  # /api/ will point here
    path('search', JobSearchView.as_view(), name='job_search'),  # /api/search
]
