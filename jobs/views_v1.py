from rest_framework import viewsets, pagination, status, filters
from rest_framework.response import Response
from django.db.models import Q
from django.utils import timezone
from datetime import timedelta
from .models import Job, Company
from .serializers import NestedJobSerializer, JobSerializer
from .query_parser import JobQueryParser, parse_query_to_search_params

class CustomPagination(pagination.PageNumberPagination):
    page_size = 20
    page_size_query_param = 'limit'
    max_page_size = 100

    def get_paginated_response(self, data):
        response = Response({
            'pagination': {
                'current': self.page.number,
                'limit': self.page.paginator.per_page,
                'total_pages': self.page.paginator.num_pages,
                'total_items': self.page.paginator.count,
            },
            'results': data
        })
        response['X-Total-Count'] = self.page.paginator.count
        
        # Link header logic
        links = []
        if self.get_next_link():
            links.append(f'<{self.get_next_link()}>; rel="next"')
        if self.get_previous_link():
            links.append(f'<{self.get_previous_link()}>; rel="prev"')
        if links:
            response['Link'] = ', '.join(links)
            
        return response

class JobViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for viewing job listings.
    """
    queryset = Job.objects.filter(is_active=True).select_related("company").prefetch_related(
        "company__industries",
        "company__staff_memberships",
    )
    serializer_class = NestedJobSerializer
    pagination_class = CustomPagination

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return NestedJobSerializer
        return NestedJobSerializer # Default

    def get_queryset(self):
        queryset = super().get_queryset()
        
        # Search
        search_query = self.request.query_params.get('search')
        if search_query:
            parser = JobQueryParser()
            components = parser.parse(search_query)
            queryset = queryset.filter(components.django_q_filters)

        # Filters
        company = self.request.query_params.get('company')
        if company:
            queryset = queryset.filter(company__name__icontains=company)

        # City maps to Job.location only (API field `city`). Prefer `city` over legacy `location`.
        city = self.request.query_params.get('city')
        location = self.request.query_params.get('location')
        if city:
            queryset = queryset.filter(location__icontains=city)
        elif location:
            queryset = queryset.filter(location__icontains=location)

        country = self.request.query_params.get('country')
        if country:
            queryset = queryset.filter(location_country__icontains=country)

        work_mode = self.request.query_params.get('work_mode')
        if work_mode:
            queryset = queryset.filter(work_mode__iexact=work_mode)

        seniority = self.request.query_params.get('seniority')
        if seniority:
            queryset = queryset.filter(seniority__iexact=seniority)

        date_posted = self.request.query_params.get('date_posted')
        if date_posted:
            now = timezone.now()
            if date_posted == 'today':
                queryset = queryset.filter(posted_at__gte=now.replace(hour=0, minute=0, second=0, microsecond=0))
            elif date_posted == 'week':
                queryset = queryset.filter(posted_at__gte=now - timedelta(days=7))
            elif date_posted == 'month':
                queryset = queryset.filter(posted_at__gte=now - timedelta(days=30))

        # Sorting
        sort = self.request.query_params.get('sort')
        if sort:
            sort_fields = sort.split(',')
            # Validate sort fields if necessary, or just try applying them
            try:
                queryset = queryset.order_by(*sort_fields)
            except Exception:
                pass # Fallback or handle invalid sort field
        else:
            queryset = queryset.order_by('-posted_at')

        return queryset

    def get_serializer(self, *args, **kwargs):
        """
        Handle field selection via the 'fields' query parameter.
        """
        fields = self.request.query_params.get('fields')
        if fields:
            kwargs['context'] = self.get_serializer_context()
            kwargs['fields'] = fields.split(',')
        return super().get_serializer(*args, **kwargs)
