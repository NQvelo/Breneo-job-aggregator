# from rest_framework import generics
# from .models import Job
# from .serializers import JobSerializer

# class JobListView(generics.ListAPIView):
#     serializer_class = JobSerializer

#     def get_queryset(self):
#         return Job.objects.all().order_by("?")


from rest_framework.views import APIView
from rest_framework.response import Response
from django.db.models import Q, Prefetch
from django.utils import timezone
from datetime import timedelta
from .models import Company, Job
from .serializers import CompanyJobsSerializer, NestedJobSerializer

class JobsGroupedByCompany(APIView):
    """
    Returns jobs grouped by company.
    Only returns companies that have active jobs.
    """

    def get(self, request):
        # Prefetch only active jobs and filter companies that have at least one active job
        companies = Company.objects.prefetch_related(
            Prefetch('jobs', queryset=Job.objects.filter(is_active=True))
        ).filter(jobs__is_active=True).distinct()
        serializer = CompanyJobsSerializer(companies, many=True)
        return Response(serializer.data)


class JobSearchView(APIView):
    """
    Search endpoint for jobs with filtering and pagination.
    Query parameters:
    - query: Search term for job title (optional)
    - country: Filter by country code (e.g., 'us', 'uk') (optional)
    - date_posted: Filter by date ('all', 'today', 'week', 'month') (optional, default: 'all')
    - page: Page number (default: 1)
    - num_pages: Number of results per page (default: 20)
    """

    def get(self, request):
        from django.core.paginator import Paginator
        
        # Get query parameters
        query = request.query_params.get('query', '').strip()
        country = request.query_params.get('country', '').strip().lower()
        date_posted = request.query_params.get('date_posted', 'all').strip().lower()
        page = int(request.query_params.get('page', 1))
        num_pages = int(request.query_params.get('num_pages', 20))
        
        # Start with active jobs only
        jobs = Job.objects.filter(is_active=True).select_related('company')
        
        # Filter by query (job title)
        if query:
            jobs = jobs.filter(
                Q(title__icontains=query) | 
                Q(description__icontains=query)
            )
        
        # Filter by country
        if country:
            # Try to match location_country field or location field
            jobs = jobs.filter(
                Q(location_country__iexact=country) |
                Q(location__icontains=country)
            )
        
        # Filter by date posted
        now = timezone.now()
        if date_posted == 'today':
            jobs = jobs.filter(posted_at__gte=now.replace(hour=0, minute=0, second=0, microsecond=0))
        elif date_posted == 'week':
            jobs = jobs.filter(posted_at__gte=now - timedelta(days=7))
        elif date_posted == 'month':
            jobs = jobs.filter(posted_at__gte=now - timedelta(days=30))
        # 'all' means no date filtering
        
        # Order by posted_at (newest first)
        jobs = jobs.order_by('-posted_at')
        
        # Pagination
        paginator = Paginator(jobs, num_pages)
        total_pages = paginator.num_pages
        total_results = paginator.count
        
        try:
            page_obj = paginator.page(page)
        except:
            page_obj = paginator.page(1)
            page = 1
        
        # Serialize jobs
        serializer = NestedJobSerializer(page_obj.object_list, many=True)
        
        # Prepare response
        response_data = {
            'results': serializer.data,
            'pagination': {
                'page': page,
                'num_pages': num_pages,
                'total_pages': total_pages,
                'total_results': total_results,
                'has_next': page_obj.has_next(),
                'has_previous': page_obj.has_previous(),
            },
            'filters': {
                'query': query,
                'country': country,
                'date_posted': date_posted,
            }
        }
        
        return Response(response_data)
