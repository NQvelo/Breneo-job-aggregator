from django.contrib import admin
from django.utils.html import format_html
from .models import Job, Company


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ("name", "logo_display", "website", "platform", "employees_count", "founded_date", "job_count")
    list_filter = ("platform",)
    search_fields = ("name", "domain", "website", "description")
    readonly_fields = ("created_at", "updated_at", "logo_display", "job_count")
    fieldsets = (
        ("Basic Information", {
            "fields": ("name", "domain", "platform", "logo", "logo_display")
        }),
        ("Company Details", {
            "fields": ("description", "website", "founded_date", "employees_count")
        }),
        ("Social & Additional", {
            "fields": ("social_links", "additional_details"),
            "classes": ("collapse",)
        }),
        ("Metadata", {
            "fields": ("created_at", "updated_at", "job_count"),
            "classes": ("collapse",)
        }),
    )
    ordering = ("name",)

    def logo_display(self, obj):
        """Display company logo as image in admin"""
        if obj.logo:
            return format_html('<img src="{}" style="max-width: 100px; max-height: 50px;" />', obj.logo)
        return "-"
    logo_display.short_description = "Logo Preview"

    def job_count(self, obj):
        """Display number of jobs for this company"""
        return obj.jobs.count()
    job_count.short_description = "Jobs"


@admin.register(Job)
class JobAdmin(admin.ModelAdmin):
    list_display = ("title", "get_company_name", "location", "platform", "posted_at", "is_active")
    list_filter = ("platform", "company", "is_active")
    search_fields = ("title", "company__name", "location", "description", "responsibilities", "qualifications", "benefits")
    ordering = ("-posted_at", "-fetched_at")
    fieldsets = (
        ("Basic Information", {
            "fields": ("title", "company", "location", "platform", "external_job_id")
        }),
        ("Job Details", {
            "fields": ("description", "responsibilities", "qualifications", "benefits", "apply_url")
        }),
        ("Metadata", {
            "fields": ("posted_at", "fetched_at", "is_active", "raw"),
            "classes": ("collapse",)
        }),
    )
    readonly_fields = ("fetched_at",)
    
    def get_company_name(self, obj):
        return obj.company.name if obj.company else "-"
    get_company_name.short_description = "Company"
    get_company_name.admin_order_field = "company__name"
