# from rest_framework import generics
# from .models import Job
# from .serializers import JobSerializer

# class JobListView(generics.ListAPIView):
#     serializer_class = JobSerializer

#     def get_queryset(self):
#         return Job.objects.all().order_by("?")


from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.db.models import Q, Prefetch
from django.utils import timezone
from datetime import timedelta
from urllib.parse import unquote
import base64
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
    By default (no query parameters), shows all active jobs with pagination.
    Query parameters:
    - query: Search term for job title, description, or company name (optional)
    - country: Filter by country code (e.g., 'us', 'uk') (optional)
    - date_posted: Filter by date ('all', 'today', 'week', 'month') (optional, default: 'all')
    - page: Page number (default: 1)
    - num_pages: Number of results per page (default: 20, max: 100)
    """

    def get(self, request):
        from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
        
        # Get query parameters with proper defaults
        query = request.query_params.get('query', '').strip()
        country = request.query_params.get('country', '').strip().lower()
        date_posted = request.query_params.get('date_posted', 'all').strip().lower()
        
        # Handle pagination parameters with validation
        try:
            page = int(request.query_params.get('page', 1))
            if page < 1:
                page = 1
        except (ValueError, TypeError):
            page = 1
        
        try:
            num_pages = int(request.query_params.get('num_pages', 20))
            if num_pages < 1:
                num_pages = 20
            elif num_pages > 100:  # Limit max results per page
                num_pages = 100
        except (ValueError, TypeError):
            num_pages = 20
        
        # Start with active jobs only, prefetch company for better performance
        jobs = Job.objects.filter(is_active=True).select_related('company')
        
        # Apply filters only if provided
        # Filter by query (job title, description, and company name)
        if query:
            # Split query into words for better matching
            query_words = query.split()
            query_filters = Q()
            
            for word in query_words:
                # Search in title, description, and company name
                query_filters |= (
                    Q(title__icontains=word) | 
                    Q(description__icontains=word) |
                    Q(company__name__icontains=word)
                )
            
            jobs = jobs.filter(query_filters)
        
        # Filter by country
        if country:
            # Try to match location_country field or location field
            # Handle common country variations
            country_variations = {
                'us': ['usa', 'united states', 'united states of america'],
                'uk': ['united kingdom', 'england', 'britain'],
                'ca': ['canada'],
            }
            
            country_filters = Q(
                location_country__iexact=country
            ) | Q(location__icontains=country)
            
            # Add variations if country code matches
            if country in country_variations:
                for variation in country_variations[country]:
                    country_filters |= Q(location__icontains=variation)
            
            jobs = jobs.filter(country_filters)
        
        # Filter by date posted (only if not 'all')
        if date_posted and date_posted != 'all':
            now = timezone.now()
            if date_posted == 'today':
                jobs = jobs.filter(posted_at__gte=now.replace(hour=0, minute=0, second=0, microsecond=0))
            elif date_posted == 'week':
                jobs = jobs.filter(posted_at__gte=now - timedelta(days=7))
            elif date_posted == 'month':
                jobs = jobs.filter(posted_at__gte=now - timedelta(days=30))
        
        # Order by posted_at (newest first), fallback to fetched_at if posted_at is null
        jobs = jobs.order_by('-posted_at', '-fetched_at')
        
        # Pagination with proper error handling
        try:
            paginator = Paginator(jobs, num_pages)
            total_pages = paginator.num_pages
            total_results = paginator.count
            
            try:
                page_obj = paginator.page(page)
            except PageNotAnInteger:
                # If page is not an integer, deliver first page
                page_obj = paginator.page(1)
                page = 1
            except EmptyPage:
                # If page is out of range, deliver last page
                page_obj = paginator.page(paginator.num_pages)
                page = paginator.num_pages
        except Exception as e:
            # Fallback if pagination fails
            return Response(
                {'error': 'Pagination error', 'detail': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        
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
                'query': query if query else None,
                'country': country if country else None,
                'date_posted': date_posted if date_posted != 'all' else None,
            }
        }
        
        return Response(response_data)


class JobDetailsView(APIView):
    """
    Get detailed information for a specific job.
    Query parameters:
    - job_id: Job ID (can be primary key ID or external_job_id, optionally URL-encoded)
    """

    def get(self, request):
        job_id = request.query_params.get('job_id', '').strip()
        
        if not job_id:
            return Response(
                {'error': 'job_id parameter is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Decode URL-encoded job_id if needed
        try:
            job_id = unquote(job_id)
        except Exception:
            pass
        
        # Try to decode base64 if it looks like base64
        try:
            if '=' in job_id or len(job_id) > 20:
                decoded = base64.b64decode(job_id + '==')  # Add padding if needed
                job_id = decoded.decode('utf-8')
        except Exception:
            pass
        
        # Try to find job by primary key first
        try:
            job = Job.objects.select_related('company').get(id=int(job_id))
        except (ValueError, Job.DoesNotExist):
            # If not found by primary key, try external_job_id
            try:
                # Try exact match on external_job_id
                job = Job.objects.select_related('company').get(external_job_id=job_id)
            except Job.DoesNotExist:
                # Try with platform if job_id contains platform info
                # Or try case-insensitive match
                job = Job.objects.select_related('company').filter(
                    Q(external_job_id__iexact=job_id) |
                    Q(external_job_id__icontains=job_id)
                ).first()
                
                if not job:
                    return Response(
                        {'error': 'Job not found'},
                        status=status.HTTP_404_NOT_FOUND
                    )
        
        # Serialize job details
        serializer = NestedJobSerializer(job)
        
        return Response(serializer.data)
