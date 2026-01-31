# Generated migration: Add matching fields for job-user matching system

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("jobs", "0015_add_workplace_type_and_skills_required"),
    ]

    operations = [
        migrations.AddField(
            model_name="job",
            name="location_country",
            field=models.CharField(
                blank=True,
                db_index=True,
                help_text="Country parsed from location for job-user matching",
                max_length=100,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="job",
            name="work_mode",
            field=models.CharField(
                choices=[
                    ("remote", "Remote"),
                    ("hybrid", "Hybrid"),
                    ("onsite", "On-site"),
                    ("unknown", "Unknown"),
                ],
                db_index=True,
                default="unknown",
                help_text="Work mode: remote, hybrid, onsite, or unknown",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="job",
            name="seniority",
            field=models.CharField(
                choices=[
                    ("intern", "Intern"),
                    ("junior", "Junior"),
                    ("mid", "Mid"),
                    ("senior", "Senior"),
                    ("lead", "Lead"),
                    ("unknown", "Unknown"),
                ],
                db_index=True,
                default="unknown",
                help_text="Seniority: intern, junior, mid, senior, lead, or unknown",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="job",
            name="role_category",
            field=models.CharField(
                blank=True,
                db_index=True,
                help_text="Role category inferred from title+skills: frontend, backend, data",
                max_length=100,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="job",
            name="min_years_experience",
            field=models.IntegerField(
                blank=True,
                help_text="Minimum years of experience required (NULL if unknown)",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="job",
            name="skills_preferred",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text="Preferred/nice-to-have skills",
            ),
        ),
        migrations.AddField(
            model_name="job",
            name="tech_stack",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text="Technologies and tools used in the role",
            ),
        ),
        migrations.AddField(
            model_name="job",
            name="languages_required",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text="Languages with CEFR level when mentioned (e.g. English C1)",
            ),
        ),
        migrations.AddField(
            model_name="job",
            name="visa_sponsorship",
            field=models.CharField(
                choices=[
                    ("yes", "Yes"),
                    ("no", "No"),
                    ("unknown", "Unknown"),
                ],
                default="unknown",
                help_text="Whether visa sponsorship is offered",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="job",
            name="work_authorization_required",
            field=models.CharField(
                choices=[
                    ("yes", "Yes"),
                    ("no", "No"),
                    ("unknown", "Unknown"),
                ],
                default="unknown",
                help_text="Whether work authorization is required",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="job",
            name="embedding_text",
            field=models.TextField(
                blank=True,
                help_text="Text used for semantic embedding (title + skills + languages)",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="job",
            name="embedding_vector",
            field=models.JSONField(
                blank=True,
                help_text="Semantic embedding vector as list of floats",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="job",
            name="data_completeness_score",
            field=models.IntegerField(
                default=0,
                help_text="Completeness score 0-100 for downranking low-quality jobs",
            ),
        ),
        migrations.AddField(
            model_name="job",
            name="is_low_quality",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="job",
            name="is_duplicate",
            field=models.BooleanField(default=False),
        ),
        migrations.AlterField(
            model_name="job",
            name="posted_at",
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),
    ]
