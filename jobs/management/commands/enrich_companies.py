import logging
from django.core.management.base import BaseCommand
from django.db.models import Q
from jobs.models import Company
from jobs.utils import (
    fetch_company_info_from_web,
    _format_employee_count,
    _parse_founded_date,
)

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Enrich company information by fetching domain, employee count, website, description, etc. from web scraping and Wikipedia"

    def add_arguments(self, parser):
        parser.add_argument(
            '--company',
            type=str,
            help='Enrich a specific company by name',
        )
        parser.add_argument(
            '--all',
            action='store_true',
            help='Enrich all companies',
        )
        parser.add_argument(
            '--missing-only',
            action='store_true',
            help='Only enrich companies missing domain or website',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be updated without actually updating',
        )

    def handle(self, *args, **options):
        dry_run = options.get('dry_run', False)
        
        # Determine which companies to process
        if options.get('company'):
            companies = Company.objects.filter(name__icontains=options['company'])
        elif options.get('all'):
            companies = Company.objects.all()
        elif options.get('missing_only'):
            companies = Company.objects.filter(
                Q(domain__isnull=True) | Q(domain='') |
                Q(website__isnull=True) | Q(website='')
            )
        else:
            self.stdout.write(self.style.ERROR('Please specify --company, --all, or --missing-only'))
            return
        
        total = companies.count()
        if total == 0:
            self.stdout.write(self.style.WARNING('No companies found to enrich.'))
            return
        
        self.stdout.write(f'Found {total} companies to enrich.')
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - No changes will be saved'))
        
        updated_count = 0
        skipped_count = 0
        error_count = 0
        
        for company in companies:
            try:
                self.stdout.write(f'\nProcessing: {company.name}...')
                
                # Fetch company info using web scraping and Wikipedia
                self.stdout.write('  Fetching company information...')
                info = fetch_company_info_from_web(company.name, domain=company.domain)
                if info:
                    self.stdout.write(self.style.SUCCESS('  ✓ Found data from web scraping/Wikipedia'))
                
                if not info:
                    self.stdout.write(self.style.WARNING('  ✗ No data found'))
                    skipped_count += 1
                    continue
                
                # Update company fields (only if they're empty or if we have better data)
                updated_fields = []
                
                if info.get("domain") and not company.domain:
                    company.domain = info["domain"]
                    updated_fields.append("domain")
                
                if info.get("website") and not company.website:
                    company.website = info["website"]
                    updated_fields.append("website")
                
                if info.get("description") and not company.description:
                    company.description = info["description"][:1000]  # Respect max_length
                    updated_fields.append("description")
                
                if info.get("employees_count") and not company.employees_count:
                    company.employees_count = info["employees_count"]
                    updated_fields.append("employees_count")
                
                if info.get("founded_date") and not company.founded_date:
                    company.founded_date = info["founded_date"]
                    updated_fields.append("founded_date")
                
                # Update social links (merge with existing)
                if info.get("social_links"):
                    current_social = company.social_links or {}
                    new_social = {k: v for k, v in info["social_links"].items() if v}
                    if new_social:
                        current_social.update(new_social)
                        company.social_links = current_social
                        updated_fields.append("social_links")
                
                # Update additional details (merge with existing)
                if info.get("additional_details"):
                    current_details = company.additional_details or {}
                    new_details = {k: v for k, v in info["additional_details"].items() if v}
                    if new_details:
                        current_details.update(new_details)
                        company.additional_details = current_details
                        updated_fields.append("additional_details")
                
                if updated_fields:
                    if not dry_run:
                        company.save(update_fields=updated_fields)
                    self.stdout.write(
                        self.style.SUCCESS(f'  ✓ Updated: {", ".join(updated_fields)}')
                    )
                    updated_count += 1
                else:
                    self.stdout.write(self.style.WARNING('  - No new data to update'))
                    skipped_count += 1
                    
            except Exception as e:
                error_count += 1
                self.stdout.write(
                    self.style.ERROR(f'  ✗ Error processing {company.name}: {str(e)}')
                )
                logger.exception(f'Error enriching company {company.name}')
        
        # Summary
        self.stdout.write('\n' + '=' * 60)
        self.stdout.write(self.style.SUCCESS('Summary:'))
        self.stdout.write(f'  Total companies processed: {total}')
        self.stdout.write(f'  Companies updated: {updated_count}')
        self.stdout.write(f'  Companies skipped: {skipped_count}')
        self.stdout.write(f'  Errors: {error_count}')
        
        if dry_run:
            self.stdout.write(self.style.WARNING('\nThis was a dry run. No changes were saved.'))
            self.stdout.write(self.style.WARNING('Run without --dry-run to apply changes.'))
        else:
            self.stdout.write(self.style.SUCCESS(f'\nSuccessfully enriched {updated_count} companies.'))
