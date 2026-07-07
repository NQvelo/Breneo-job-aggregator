from django.contrib import admin

from .models import Interview, InterviewAttempt, InterviewQuestion


class InterviewQuestionInline(admin.TabularInline):
    model = InterviewQuestion
    extra = 0
    readonly_fields = ("id",)


@admin.register(Interview)
class InterviewAdmin(admin.ModelAdmin):
    list_display = ("id", "user_id", "job_position", "created_at")
    list_filter = ("created_at",)
    search_fields = ("job_position", "user_id")
    readonly_fields = ("id", "created_at")
    inlines = [InterviewQuestionInline]


@admin.register(InterviewQuestion)
class InterviewQuestionAdmin(admin.ModelAdmin):
    list_display = ("id", "interview", "order", "question_text")
    search_fields = ("question_text",)
    readonly_fields = ("id",)


@admin.register(InterviewAttempt)
class InterviewAttemptAdmin(admin.ModelAdmin):
    list_display = ("id", "question", "overall_score", "is_completed", "created_at")
    list_filter = ("is_completed", "created_at")
    readonly_fields = ("id", "created_at")
