from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status
from .models import Job, Company
from django.utils import timezone
from datetime import timedelta

class APIV1TestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.company = Company.objects.create(name='Test Company', platform='test')
        self.company2 = Company.objects.create(name='Another Corp', platform='test2')
        
        # Job 1: Remote Senior Python Dev in Berlin (posted today)
        self.job1 = Job.objects.create(
            title='Senior Python Engineer',
            company=self.company,
            location='Berlin',
            location_country='Germany',
            work_mode='remote',
            seniority='senior',
            posted_at=timezone.now(),
            is_active=True,
            external_job_id='ext1',
            skills_required=['Python', 'Django', 'AWS']
        )
        
        # Job 2: Onsite Junior React Dev in SF (posted 2 days ago)
        self.job2 = Job.objects.create(
            title='Junior Frontend Developer',
            company=self.company,
            location='San Francisco',
            location_country='USA',
            work_mode='onsite',
            seniority='junior',
            posted_at=timezone.now() - timedelta(days=2),
            is_active=True,
            external_job_id='ext2',
            skills_required=['React', 'TypeScript', 'CSS']
        )
        
        # Job 3: Hybrid Mid Java Dev in London (posted 8 days ago)
        self.job3 = Job.objects.create(
            title='Mid Java Developer',
            company=self.company2,
            location='London',
            work_mode='hybrid',
            seniority='mid',
            posted_at=timezone.now() - timedelta(days=8),
            is_active=True,
            external_job_id='ext3',
            skills_required=['Java', 'Spring', 'SQL']
        )

    def test_list_jobs(self):
        url = reverse('job-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 3)
        self.assertIn('pagination', response.data)
        self.assertEqual(response.data['pagination']['total_items'], 3)

    def test_search_by_title(self):
        url = reverse('job-list')
        response = self.client.get(url, {'search': 'Python'})
        self.assertEqual(len(response.data['results']), 1)
        self.assertEqual(response.data['results'][0]['title'], 'Senior Python Engineer')

    def test_search_by_skill(self):
        # Searching for "Django" should find job1 even though it's not in the title
        url = reverse('job-list')
        response = self.client.get(url, {'search': 'Django'})
        self.assertEqual(len(response.data['results']), 1)
        self.assertEqual(response.data['results'][0]['title'], 'Senior Python Engineer')

    def test_filter_location_partial(self):
        url = reverse('job-list')
        response = self.client.get(url, {'location': 'San'})
        self.assertEqual(len(response.data['results']), 1)
        self.assertEqual(response.data['results'][0]['location'], 'San Francisco')

    def test_list_includes_city_and_country(self):
        url = reverse('job-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        by_id = {r['id']: r for r in response.data['results']}
        r1 = by_id[self.job1.id]
        self.assertEqual(r1['city'], 'Berlin')
        self.assertEqual(r1['country'], 'Germany')
        self.assertEqual(r1['location'], 'Berlin')
        self.assertEqual(r1['location_country'], 'Germany')
        r3 = by_id[self.job3.id]
        self.assertEqual(r3['city'], 'London')
        self.assertEqual(r3['country'], '')

    def test_filter_country(self):
        url = reverse('job-list')
        response = self.client.get(url, {'country': 'Germany'})
        self.assertEqual(len(response.data['results']), 1)
        self.assertEqual(response.data['results'][0]['id'], self.job1.id)

    def test_filter_work_mode(self):
        url = reverse('job-list')
        response = self.client.get(url, {'work_mode': 'remote'})
        self.assertEqual(len(response.data['results']), 1)
        self.assertEqual(response.data['results'][0]['work_mode'], 'remote')

    def test_filter_seniority(self):
        url = reverse('job-list')
        response = self.client.get(url, {'seniority': 'junior'})
        self.assertEqual(len(response.data['results']), 1)
        self.assertEqual(response.data['results'][0]['seniority'], 'junior')

    def test_filter_company(self):
        url = reverse('job-list')
        response = self.client.get(url, {'company': 'Another'})
        self.assertEqual(len(response.data['results']), 1)
        self.assertEqual(response.data['results'][0]['company']['name'], 'Another Corp')

    def test_filter_date_posted(self):
        url = reverse('job-list')
        
        # Today
        response = self.client.get(url, {'date_posted': 'today'})
        self.assertEqual(len(response.data['results']), 1)
        self.assertEqual(response.data['results'][0]['id'], self.job1.id)
        
        # Week (should include job1 (today) and job2 (2 days ago))
        response = self.client.get(url, {'date_posted': 'week'})
        self.assertEqual(len(response.data['results']), 2)
        
        # Month (should include all 3)
        response = self.client.get(url, {'date_posted': 'month'})
        self.assertEqual(len(response.data['results']), 3)

    def test_sorting_posted_at_desc(self):
        url = reverse('job-list')
        # -posted_at means newest first
        response = self.client.get(url, {'sort': '-posted_at'})
        results = response.data['results']
        self.assertEqual(results[0]['id'], self.job1.id) # Today
        self.assertEqual(results[1]['id'], self.job2.id) # 2 days ago
        self.assertEqual(results[2]['id'], self.job3.id) # 8 days ago

    def test_sorting_title_asc(self):
        url = reverse('job-list')
        response = self.client.get(url, {'sort': 'title'})
        results = response.data['results']
        # Alphabetical: J(unior), M(id), S(enior)
        self.assertEqual(results[0]['title'], 'Junior Frontend Developer')
        self.assertEqual(results[1]['title'], 'Mid Java Developer')
        self.assertEqual(results[2]['title'], 'Senior Python Engineer')

    def test_pagination(self):
        url = reverse('job-list')
        # Limit 1, Page 1
        response = self.client.get(url, {'page': 1, 'limit': 1})
        self.assertEqual(len(response.data['results']), 1)
        self.assertEqual(response.data['pagination']['current'], 1)
        self.assertEqual(response.data['pagination']['total_pages'], 3)
        
        # Limit 1, Page 2
        response = self.client.get(url, {'page': 2, 'limit': 1})
        self.assertEqual(len(response.data['results']), 1)
        # Verify it's a different job than page 1 (assuming default sort order)
        
    def test_field_selection(self):
        url = reverse('job-list')
        response = self.client.get(url, {'fields': 'id,title,location'})
        result = response.data['results'][0]
        self.assertIn('id', result)
        self.assertIn('title', result)
        self.assertIn('location', result)
        self.assertNotIn('work_mode', result)
        self.assertNotIn('company', result) # Company is a nested serializer, shouldn't be main level unless requested
