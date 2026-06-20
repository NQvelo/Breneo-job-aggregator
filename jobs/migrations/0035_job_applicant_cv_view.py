import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("jobs", "0034_company_staff_membership_status"),
    ]

    operations = [
        migrations.CreateModel(
            name="JobApplicantCvView",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("applicant_user_id", models.CharField(db_index=True, max_length=255)),
                ("viewer_user_id", models.CharField(db_index=True, max_length=255)),
                ("first_viewed_at", models.DateTimeField()),
                ("last_viewed_at", models.DateTimeField()),
                ("view_count", models.PositiveIntegerField(default=1)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "application",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="cv_views",
                        to="jobs.jobapplication",
                    ),
                ),
                (
                    "job",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="applicant_cv_views",
                        to="jobs.job",
                    ),
                ),
            ],
            options={
                "db_table": "job_applicant_cv_views",
                "ordering": ["-last_viewed_at", "-id"],
            },
        ),
        migrations.AddConstraint(
            model_name="jobapplicantcvview",
            constraint=models.UniqueConstraint(
                fields=("job", "applicant_user_id", "viewer_user_id"),
                name="uniq_job_applicant_cv_view",
            ),
        ),
    ]
