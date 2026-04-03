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
from .serializers import (
    CompanyJobsSerializer,
    NestedJobSerializer,
    CompanyDetailSerializer,
    EmployerJobCreateSerializer,
    EmployerJobUpdateSerializer,
)
from .permissions import CanPostEmployerJob
from .employer_jobs import create_employer_job, get_employer_job_or_none, update_employer_job

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


def _get_multi_value_param(request, key, split_comma=True):
    """Get a list of non-empty values from query params. Supports ?key=a,b,c or ?key=a&key=b."""
    values = request.query_params.getlist(key)
    if not values and key in request.query_params:
        single = request.query_params.get(key, '').strip()
        if single and split_comma:
            values = [v.strip() for v in single.split(',') if v.strip()]
        elif single:
            values = [single]
    else:
        # Flatten: split each value by comma so "us,uk" from getlist becomes ["us", "uk"]
        result = []
        for v in values:
            if not v or not v.strip():
                continue
            v = v.strip()
            if split_comma:
                for part in v.split(','):
                    if part.strip():
                        result.append(part.strip())
            else:
                result.append(v)
        values = result
    return values


class JobSearchView(APIView):
    """
    Search endpoint for jobs with NLP-based filtering and pagination.
    By default (no query parameters), shows all active jobs with pagination.
    
    Query parameters (multi-value: when 2+ items, separate with comma, e.g. title=Engineer,Developer and country=us,uk):
    - query: Natural language search query for job titles (optional)
    - title_filter: Direct title filter string (Google-like syntax) (optional)
    - title: One or more title keywords, comma-separated; job matches if title contains ANY (e.g. title=Engineer,Developer)
    - country: One or more country codes, comma-separated (e.g. country=us,uk)
    - location_country: One or more location country names, comma-separated (e.g. location_country=USA,Germany)
    - role_category: One or more, comma-separated (e.g. role_category=frontend,backend,data)
    - work_mode: One or more, comma-separated (e.g. work_mode=remote,hybrid,onsite)
    - seniority: One or more, comma-separated (e.g. seniority=senior,junior,mid)
    - company: One or more company names, comma-separated (e.g. company=Stripe,Airbnb)
    - date_posted: 'all', 'today', 'week', 'month' (optional, default: 'all')
    - recent: 'true' to show only jobs fetched in last 24 hours (optional)
    - sort: 'newest', 'oldest', 'recently_fetched' (optional, default: 'newest')
    - offset, limit OR page, num_pages: pagination
    """

    def get(self, request):
        from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
        from .query_parser import parse_query_to_search_params, JobQueryParser
        
        # Get query parameters
        user_query = request.query_params.get('query', '').strip()
        title_filter = request.query_params.get('title_filter', '').strip()
        date_posted = request.query_params.get('date_posted', 'all').strip().lower()
        recent = request.query_params.get('recent', '').strip().lower() == 'true'
        sort_order = request.query_params.get('sort', 'newest').strip().lower()

        # Multi-value filters (list of values; job matches if it matches ANY)
        countries = _get_multi_value_param(request, 'country')
        location_countries = _get_multi_value_param(request, 'location_country')
        title_keywords = _get_multi_value_param(request, 'title')
        role_categories = _get_multi_value_param(request, 'role_category')
        work_modes = _get_multi_value_param(request, 'work_mode')
        seniorities = _get_multi_value_param(request, 'seniority')
        company_names = _get_multi_value_param(request, 'company')
        
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
        
        # Apply title filter (from query / title_filter)
        if title_q_filter:
            jobs = jobs.filter(title_q_filter)
        
        # Multi-value title keywords: job matches if title contains ANY
        if title_keywords:
            title_kw_q = Q()
            for kw in title_keywords:
                title_kw_q |= Q(title__icontains=kw)
            jobs = jobs.filter(title_kw_q)
        
        # Multi-value country filter (code or variations, e.g. us, uk)
        country_variations = {
            'us': ['usa', 'united states', 'united states of america', 'us'],
            'uk': ['united kingdom', 'england', 'britain', 'uk'],
            'ca': ['canada', 'ca'],
            'de': ['germany', 'deutschland'],
            'fr': ['france'],
            'au': ['australia'],
            'in': ['india'],
            'nl': ['netherlands', 'holland'],
        }
        if countries:
            country_q = Q()
            for code in countries:
                code = code.lower()
                country_q |= Q(location__icontains=code)
                country_q |= Q(location_country__icontains=code)
                if code in country_variations:
                    for v in country_variations[code]:
                        country_q |= Q(location__icontains=v)
                        country_q |= Q(location_country__icontains=v)
            jobs = jobs.filter(country_q)
        
        # Multi-value location_country (exact names, e.g. USA, Germany)
        if location_countries:
            loc_q = Q()
            for loc in location_countries:
                loc_q |= Q(location_country__icontains=loc)
            jobs = jobs.filter(loc_q)
        
        # Multi-value role_category
        if role_categories:
            role_q = Q()
            for r in role_categories:
                role_q |= Q(role_category__iexact=r)
            jobs = jobs.filter(role_q)
        
        # Multi-value work_mode
        if work_modes:
            mode_q = Q()
            for m in work_modes:
                mode_q |= Q(work_mode__iexact=m)
            jobs = jobs.filter(mode_q)
        
        # Multi-value seniority
        if seniorities:
            sen_q = Q()
            for s in seniorities:
                sen_q |= Q(seniority__iexact=s)
            jobs = jobs.filter(sen_q)
        
        # Multi-value company name
        if company_names:
            company_q = Q()
            for name in company_names:
                company_q |= Q(company__name__icontains=name)
            jobs = jobs.filter(company_q)
        
        # Filter by date posted (only if not 'all')
        if date_posted and date_posted != 'all':
            now = timezone.now()
            if date_posted == 'today':
                jobs = jobs.filter(posted_at__gte=now.replace(hour=0, minute=0, second=0, microsecond=0))
            elif date_posted == 'week':
                jobs = jobs.filter(posted_at__gte=now - timedelta(days=7))
            elif date_posted == 'month':
                jobs = jobs.filter(posted_at__gte=now - timedelta(days=30))
        
        # Filter by recently fetched (last 24 hours)
        if recent:
            now = timezone.now()
            recent_threshold = now - timedelta(hours=24)
            jobs = jobs.filter(fetched_at__gte=recent_threshold)
        
        # Sort jobs
        if sort_order == 'recently_fetched':
            # Sort by fetched_at (most recently fetched first)
            jobs = jobs.order_by('-fetched_at', '-posted_at')
        elif sort_order == 'oldest':
            # Sort by posted_at (oldest first)
            jobs = jobs.order_by('posted_at', 'fetched_at')
        else:
            # Default: newest first (by posted_at, fallback to fetched_at)
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
                'title': title_keywords if title_keywords else None,
                'country': countries if countries else None,
                'location_country': location_countries if location_countries else None,
                'role_category': role_categories if role_categories else None,
                'work_mode': work_modes if work_modes else None,
                'seniority': seniorities if seniorities else None,
                'company': company_names if company_names else None,
                'date_posted': date_posted if date_posted != 'all' else None,
                'recent': recent,
                'sort': sort_order,
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


class EmployerJobCreateView(APIView):
    """
    Create a job posted by an employer. Full description is stored in `raw` (employer payload + body)
    and in `description` so the same parsing/normalization pipeline as fetched jobs runs.

    Auth: set env EMPLOYER_POST_SECRET and send header X-Employer-Key: <secret>, OR use a
    logged-in user in the Django group "Employer".

    POST JSON body:
    - title, company (name), location (optional), work_mode (remote|hybrid|onsite|on-site|unknown)
    - full_description (full text; responsibilities/qualifications/etc. derived on save)
    - salary (optional), apply_url (optional), is_active (default true)
    """

    # Empty auth classes: if we use Session/Basic here, DRF turns a failed permission into
    # NotAuthenticated ("credentials not provided") when no session/basic succeeds — even when
    # the real check is X-Employer-Key (see APIView.permission_denied).
    authentication_classes = []
    permission_classes = [CanPostEmployerJob]

    def get(self, request):
        """
        Employer dashboard listing (includes active + inactive jobs).
        Filter by company, not platform:
        - ?company_id=<id> (preferred)
        - ?company=<exact company name>
        """
        jobs = Job.objects.select_related("company")
        company_id = request.query_params.get("company_id", "").strip()
        company_name = request.query_params.get("company", "").strip()

        if company_id:
            try:
                jobs = jobs.filter(company_id=int(company_id))
            except ValueError:
                return Response({"error": "company_id must be an integer"}, status=status.HTTP_400_BAD_REQUEST)
        elif company_name:
            jobs = jobs.filter(company__name__iexact=company_name)

        jobs = jobs.order_by("-posted_at", "-fetched_at")
        serializer = NestedJobSerializer(jobs, many=True)
        return Response(serializer.data)

    def post(self, request):
        ser = EmployerJobCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data
        job = create_employer_job(
            title=data["title"],
            company_name=data["company"],
            location=data.get("location") or "",
            work_mode=data["work_mode"],
            full_description=data["full_description"],
            salary=data.get("salary") or "",
            apply_url=data.get("apply_url") or None,
            is_active=data.get("is_active", True),
        )
        out = NestedJobSerializer(job).data
        return Response(out, status=status.HTTP_201_CREATED)


def _resolve_employer_job(request, job_id: int):
    """
    Load job by primary key. If ?company_id= is present, require job.company_id to match.
    Returns (job, error_tag): error_tag is None, "not_found", or "bad_request".
    """
    job = get_employer_job_or_none(job_id)
    if not job:
        return None, "not_found"
    company_id = request.query_params.get("company_id", "").strip()
    if company_id:
        try:
            if job.company_id != int(company_id):
                return None, "not_found"
        except ValueError:
            return None, "bad_request"
    return job, None


class EmployerJobDetailView(APIView):
    """
    Single employer job by primary key.

    GET    /api/employer/jobs/<job_id>  — full nested job payload
    PATCH  /api/employer/jobs/<job_id>  — partial update (JSON body)
    POST   /api/employer/jobs/<job_id>  — same as PATCH (for clients that cannot send PATCH)
    DELETE /api/employer/jobs/<job_id>  — remove job

    Optional query (all methods): ?company_id=<id> to scope access to that company’s jobs.
    """

    authentication_classes = []
    permission_classes = [CanPostEmployerJob]

    def get(self, request, job_id: int):
        job, err = _resolve_employer_job(request, job_id)
        if err == "bad_request":
            return Response({"error": "company_id must be an integer"}, status=status.HTTP_400_BAD_REQUEST)
        if err == "not_found" or job is None:
            return Response({"error": "Job not found"}, status=status.HTTP_404_NOT_FOUND)

        return Response(NestedJobSerializer(job).data)

    def _update(self, request, job_id: int):
        job, err = _resolve_employer_job(request, job_id)
        if err == "bad_request":
            return Response({"error": "company_id must be an integer"}, status=status.HTTP_400_BAD_REQUEST)
        if err == "not_found" or job is None:
            return Response({"error": "Job not found"}, status=status.HTTP_404_NOT_FOUND)

        ser = EmployerJobUpdateSerializer(data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data

        if not data:
            return Response({"error": "No fields provided for update"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            updated = update_employer_job(job, data)
        except ValueError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(NestedJobSerializer(updated).data, status=status.HTTP_200_OK)

    def patch(self, request, job_id: int):
        return self._update(request, job_id)

    def post(self, request, job_id: int):
        """Alias for PATCH — update job with JSON body."""
        return self._update(request, job_id)

    def delete(self, request, job_id: int):
        job, err = _resolve_employer_job(request, job_id)
        if err == "bad_request":
            return Response({"error": "company_id must be an integer"}, status=status.HTTP_400_BAD_REQUEST)
        if err == "not_found" or job is None:
            return Response({"error": "Job not found"}, status=status.HTTP_404_NOT_FOUND)
        job.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class TriggerFetchView(APIView):
    """
    Trigger endpoint to manually fetch jobs.
    Can be called by external cron services or webhooks.
    
    Query parameters:
    - secret: Secret token for authentication (optional, set FETCH_SECRET env var)
    """
    
    def post(self, request):
        import os
        from django.core.management import call_command
        from io import StringIO
        
        # Optional authentication via secret token
        secret = request.query_params.get('secret') or request.data.get('secret')
        expected_secret = os.environ.get('FETCH_SECRET')
        
        if expected_secret and secret != expected_secret:
            return Response(
                {'error': 'Unauthorized'},
                status=status.HTTP_401_UNAUTHORIZED
            )
        
        try:
            # Capture output
            output = StringIO()
            
            # Run fetch_jobs command
            call_command('fetch_jobs', stdout=output)
            
            output_str = output.getvalue()
            
            return Response({
                'status': 'success',
                'message': 'Job fetching completed',
                'output': output_str
            })
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.exception("Error triggering fetch_jobs")
            return Response(
                {
                    'status': 'error',
                    'message': 'Failed to fetch jobs',
                    'error': str(e)
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def get(self, request):
        """Allow GET requests for easy cron job calling"""
        return self.post(request)
