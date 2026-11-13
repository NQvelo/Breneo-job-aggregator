from django.contrib import admin

from .models import Interview, InterviewAttempt, InterviewQuestion, InterviewRole, RoleQuestion


class InterviewQuestionInline(admin.TabularInline):
    model = InterviewQuestion
    extra = 0
    readonly_fields = ("id",)


class RoleQuestionInline(admin.TabularInline):
    model = RoleQuestion
    extra = 0
    ordering = ("position",)


@admin.register(InterviewRole)
class InterviewRoleAdmin(admin.ModelAdmin):
    list_display = ("slug", "title", "title_ka")
    search_fields = ("slug", "title", "title_ka")
    inlines = [RoleQuestionInline]


@admin.register(RoleQuestion)
class RoleQuestionAdmin(admin.ModelAdmin):
    list_display = ("role", "position", "question_text")
    list_filter = ("role",)
    search_fields = ("question_text", "role__slug", "role__title")
    ordering = ("role", "position")


@admin.register(Interview)
class InterviewAdmin(admin.ModelAdmin):
    list_display = ("id", "user_id", "role", "job", "job_position", "created_at")
    list_filter = ("created_at",)
    search_fields = ("job_position", "user_id")
    readonly_fields = ("id", "created_at")
    raw_id_fields = ("job",)
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
