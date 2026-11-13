from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.http import HttpResponse
from django.urls import path, include

from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView

from django.views.generic import TemplateView

from jobs.internal_match_views import JobMatchOneView, JobMatchesView


def health(request):
    """Minimal health check: no DB, no template. Use for Railway/load balancer health checks."""
    return HttpResponse("ok", content_type="text/plain")


urlpatterns = [
    path("health/", health),
    path("internal/job-matches", JobMatchesView.as_view(), name="internal_job_matches"),
    path("internal/job-matches/", JobMatchesView.as_view(), name="internal_job_matches_slash"),
    path("internal/job-matches/one", JobMatchOneView.as_view(), name="internal_job_match_one"),
    path("internal/job-matches/one/", JobMatchOneView.as_view(), name="internal_job_match_one_slash"),
    path('', TemplateView.as_view(template_name='index.html'), name='home'),
    path('admin/', admin.site.urls),
    path('api/', include('jobs.urls')),
    path('api/v1/', include('jobs.urls_v1')),
    path('api/v1/interview/', include('interview_api.urls')),
    # OpenAPI Schema and Documentation
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
]

# Serve static files in development (DEBUG=True)
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
