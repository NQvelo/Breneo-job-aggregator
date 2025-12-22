from rest_framework import generics
from .models import Job
from .serializers import JobSerializer

class JobListView(generics.ListAPIView):
    serializer_class = JobSerializer

    def get_queryset(self):
        return Job.objects.all().order_by("?")

