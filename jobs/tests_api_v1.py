from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status
from .models import Job, Company
from django.utils import timezone

class APIV1TestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.company = Company.objects.create(name='Test Company', platform='test')
        self.job1 = Job.objects.create(
            title='Software Engineer',
            company=self.company,
            location='Berlin',
            work_mode='remote',
            seniority='senior',
            posted_at=timezone.now(),
            is_active=True,
            external_job_id='ext1'
        )
        self.job2 = Job.objects.create(
            title='Product Manager',
            company=self.company,
            location='San Francisco',
            work_mode='onsite',
            seniority='junior',
            posted_at=timezone.now() - timezone.timedelta(days=2),
            is_active=True,
            external_job_id='ext2'
        )

    def test_list_jobs(self):
        url = reverse('job-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 2)
        self.assertIn('pagination', response.data)
        self.assertIn('X-Total-Count', response)

    def test_retrieve_job(self):
        url = reverse('job-detail', kwargs={'pk': self.job1.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['title'], 'Software Engineer')

    def test_filter_jobs(self):
        url = reverse('job-list')
        response = self.client.get(url, {'location': 'Berlin'})
        self.assertEqual(len(response.data['results']), 1)
        self.assertEqual(response.data['results'][0]['title'], 'Software Engineer')

    def test_search_jobs(self):
        url = reverse('job-list')
        response = self.client.get(url, {'search': 'Product'})
        self.assertEqual(len(response.data['results']), 1)
        self.assertEqual(response.data['results'][0]['title'], 'Product Manager')

    def test_sorting_jobs(self):
        url = reverse('job-list')
        response = self.client.get(url, {'sort': 'posted_at'}) # oldest first
        self.assertEqual(response.data['results'][0]['title'], 'Product Manager')

    def test_field_selection(self):
        url = reverse('job-list')
        response = self.client.get(url, {'fields': 'id,title'})
        self.assertEqual(len(response.data['results'][0]), 2)
        self.assertIn('id', response.data['results'][0])
        self.assertIn('title', response.data['results'][0])
        self.assertNotIn('company', response.data['results'][0])

    def test_error_handling(self):
        url = reverse('job-detail', kwargs={'pk': 999})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertIn('error', response.data)
        self.assertIn('status_code', response.data)
