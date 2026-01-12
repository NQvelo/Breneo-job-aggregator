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
from .serializers import CompanyJobsSerializer, NestedJobSerializer, CompanyDetailSerializer

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
    Search endpoint for jobs with NLP-based filtering and pagination.
    By default (no query parameters), shows all active jobs with pagination.
    
    Query parameters:
    - query: Natural language search query for job titles (optional)
        Examples:
        - "software engineer"
        - '"Software Engineer"'
        - "backend OR frontend"
        - "developer -senior"
        - "engineer not senior"
    - title_filter: Direct title filter string (Google-like syntax) (optional)
        If provided, takes precedence over 'query' parameter
    - country: Filter by country code (e.g., 'us', 'uk') (optional)
    - date_posted: Filter by date ('all', 'today', 'week', 'month') (optional, default: 'all')
    - offset: Offset for pagination (default: 0)
    - limit: Number of results per page (default: 20, max: 100)
    - page: Page number (alternative to offset, default: 1)
    - num_pages: Number of results per page (alternative to limit, default: 20, max: 100)
    """

    def get(self, request):
        from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
        from .query_parser import parse_query_to_search_params, JobQueryParser
        
        # Get query parameters
        user_query = request.query_params.get('query', '').strip()
        title_filter = request.query_params.get('title_filter', '').strip()
        country = request.query_params.get('country', '').strip().lower()
        date_posted = request.query_params.get('date_posted', 'all').strip().lower()
        
        # Handle pagination - support both offset/limit and page/num_pages
        try:
            offset = int(request.query_params.get('offset', 0))
            if offset < 0:
                offset = 0
        except (ValueError, TypeError):
            offset = 0
        
        try:
            limit = int(request.query_params.get('limit', 0))
            if limit < 1:
                limit = 0  # Will use page/num_pages if limit not provided
            elif limit > 100:
                limit = 100
        except (ValueError, TypeError):
            limit = 0
        
        # Handle legacy pagination parameters
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
            elif num_pages > 100:
                num_pages = 100
        except (ValueError, TypeError):
            num_pages = 20
        
        # Use offset/limit if provided, otherwise use page/num_pages
        use_offset_limit = limit > 0
        if not use_offset_limit:
            limit = num_pages
        
        # Start with active jobs only, prefetch company for better performance
        jobs = Job.objects.filter(is_active=True).select_related('company')
        
        # Apply title filter using NLP parser
        title_q_filter = Q()
        parsed_title_filter = None
        
        if title_filter:
            # Use direct title_filter string
            parser = JobQueryParser()
            components = parser.parse(title_filter)
            title_q_filter = components.django_q_filters
            parsed_title_filter = components.title_filter
        elif user_query:
            # Parse natural language query
            search_params = parse_query_to_search_params(user_query, offset=offset, limit=limit)
            title_q_filter = search_params['django_q_filters']
            parsed_title_filter = search_params['title_filter']
        
        # Apply title filter
        if title_q_filter:
            jobs = jobs.filter(title_q_filter)
        
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
        
        # Get total count before pagination
        total_results = jobs.count()
        
        # Apply pagination
        if use_offset_limit:
            # Use offset/limit pagination
            jobs_list = list(jobs[offset:offset + limit])
            total_pages = (total_results + limit - 1) // limit if limit > 0 else 1
            current_page = (offset // limit) + 1 if limit > 0 else 1
            has_next = (offset + limit) < total_results
            has_previous = offset > 0
        else:
            # Use page-based pagination
            try:
                paginator = Paginator(jobs, num_pages)
                total_pages = paginator.num_pages
                
                try:
                    page_obj = paginator.page(page)
                    jobs_list = list(page_obj.object_list)
                    current_page = page
                    has_next = page_obj.has_next()
                    has_previous = page_obj.has_previous()
                except PageNotAnInteger:
                    page_obj = paginator.page(1)
                    jobs_list = list(page_obj.object_list)
                    current_page = 1
                    has_next = page_obj.has_next()
                    has_previous = page_obj.has_previous()
                except EmptyPage:
                    page_obj = paginator.page(paginator.num_pages)
                    jobs_list = list(page_obj.object_list)
                    current_page = paginator.num_pages
                    has_next = False
                    has_previous = page_obj.has_previous()
            except Exception as e:
                # Fallback if pagination fails
                return Response(
                    {'error': 'Pagination error', 'detail': str(e)},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
        
        # Serialize jobs
        serializer = NestedJobSerializer(jobs_list, many=True)
        
        # Prepare response
        response_data = {
            'results': serializer.data,
            'pagination': {
                'offset': offset if use_offset_limit else None,
                'limit': limit if use_offset_limit else None,
                'page': current_page if not use_offset_limit else None,
                'num_pages': num_pages if not use_offset_limit else None,
                'total_pages': total_pages,
                'total_results': total_results,
                'has_next': has_next,
                'has_previous': has_previous,
            },
            'filters': {
                'query': user_query if user_query else None,
                'title_filter': parsed_title_filter if parsed_title_filter else None,
                'country': country if country else None,
                'date_posted': date_posted if date_posted != 'all' else None,
            }
        }
        
        return Response(response_data)


class CompanyDetailView(APIView):
    """
    Get detailed information for a specific company.
    Query parameters:
    - name: Company name (case-insensitive search)
    - id: Company ID (alternative to name)
    
    URL path parameter:
    - company_name: Company name in URL path (e.g., /api/companies/Airbnb)
    """
    
    def get(self, request, company_name=None):
        from urllib.parse import unquote
        
        # Get company name from URL path or query parameter
        if company_name:
            # URL path parameter (e.g., /api/companies/Airbnb)
            company_name = unquote(company_name).strip()
        else:
            # Query parameter (e.g., /api/companies?name=Airbnb)
            company_name = request.query_params.get('name', '').strip()
            company_id = request.query_params.get('id', '').strip()
            
            if company_id:
                try:
                    company = Company.objects.get(id=int(company_id))
                    serializer = CompanyDetailSerializer(company)
                    return Response(serializer.data)
                except (ValueError, Company.DoesNotExist):
                    return Response(
                        {'error': 'Company not found'},
                        status=status.HTTP_404_NOT_FOUND
                    )
        
        if not company_name:
            return Response(
                {'error': 'Company name or ID is required. Use ?name=CompanyName or ?id=123'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Try to find company by name (case-insensitive)
        try:
            company = Company.objects.get(name__iexact=company_name)
        except Company.DoesNotExist:
            # Try partial match
            companies = Company.objects.filter(name__icontains=company_name)
            if companies.count() == 1:
                company = companies.first()
            elif companies.count() > 1:
                # Multiple matches, return list
                serializer = CompanyDetailSerializer(companies, many=True)
                return Response({
                    'matches': serializer.data,
                    'message': f'Multiple companies found matching "{company_name}". Please be more specific.'
                })
            else:
                return Response(
                    {'error': f'Company not found: {company_name}'},
                    status=status.HTTP_404_NOT_FOUND
                )
        
        serializer = CompanyDetailSerializer(company)
        return Response(serializer.data)


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
