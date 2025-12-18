from django.contrib import admin
from .models import Job


@admin.register(Job)
class JobAdmin(admin.ModelAdmin):
	list_display = ("title", "company", "location", "platform", "posted_at", "is_active")
	list_filter = ("platform", "company", "is_active")
	search_fields = ("title", "company", "location")
	ordering = ("-posted_at", "-fetched_at")
