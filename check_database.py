#!/usr/bin/env python
"""
Quick diagnostic script to check database status and jobs count.
Run this to verify database connection and data.
"""
import os
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'job_aggregator.settings')
django.setup()

from django.db import connection
from jobs.models import Company, Job

def check_database():
    print("=" * 60)
    print("DATABASE DIAGNOSTIC")
    print("=" * 60)
    
    # Check database connection
    try:
        connection.ensure_connection()
        print(f"✅ Database connected: {connection.settings_dict['ENGINE']}")
        
        if 'postgresql' in connection.settings_dict['ENGINE']:
            db_name = connection.settings_dict.get('NAME', 'Unknown')
            print(f"   PostgreSQL database: {db_name}")
        else:
            db_path = connection.settings_dict.get('NAME', 'Unknown')
            print(f"   SQLite database: {db_path}")
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        return
    
    print()
    
    # Count companies
    try:
        company_count = Company.objects.count()
        print(f"📊 Companies in database: {company_count}")
        
        if company_count > 0:
            companies = Company.objects.all()[:5]
            print(f"   Sample companies:")
            for comp in companies:
                print(f"     - {comp.name}")
    except Exception as e:
        print(f"❌ Error counting companies: {e}")
    
    print()
    
    # Count jobs
    try:
        total_jobs = Job.objects.count()
        active_jobs = Job.objects.filter(is_active=True).count()
        inactive_jobs = Job.objects.filter(is_active=False).count()
        
        print(f"📊 Jobs in database:")
        print(f"   Total: {total_jobs}")
        print(f"   Active: {active_jobs}")
        print(f"   Inactive: {inactive_jobs}")
        
        if active_jobs > 0:
            print(f"\n   Sample active jobs:")
            jobs = Job.objects.filter(is_active=True).select_related('company')[:5]
            for job in jobs:
                print(f"     - {job.title} @ {job.company.name}")
        elif total_jobs > 0:
            print(f"\n   ⚠️  Warning: All jobs are inactive!")
            print(f"   Jobs won't appear in API if is_active=False")
        
        if total_jobs == 0:
            print(f"\n   ❌ Database is empty!")
            print(f"   You need to run: python manage.py fetch_jobs")
            
    except Exception as e:
        print(f"❌ Error counting jobs: {e}")
    
    print()
    print("=" * 60)
    
    # Recommendations
    if total_jobs == 0:
        print("\n💡 RECOMMENDATION:")
        print("   Database is empty. Run:")
        print("   python manage.py fetch_jobs")
    elif active_jobs == 0 and total_jobs > 0:
        print("\n💡 RECOMMENDATION:")
        print("   All jobs are inactive. Run:")
        print("   python manage.py fetch_jobs")
        print("   (This will mark old jobs inactive and fetch new ones)")
    elif active_jobs > 0:
        print("\n✅ Database looks good!")
        print(f"   API should return {active_jobs} active jobs")
        print(f"   Check: GET /api/search or GET /api/")

if __name__ == '__main__':
    check_database()
