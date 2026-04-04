import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("jobs", "0019_add_job_salary"),
    ]

    operations = [
        migrations.CreateModel(
            name="Industry",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=200, unique=True)),
                ("slug", models.SlugField(blank=True, max_length=220, unique=True)),
                ("description", models.TextField(blank=True, help_text="Optional notes", null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name_plural": "Industries",
                "ordering": ["name"],
            },
        ),
        migrations.AddField(
            model_name="company",
            name="company_email",
            field=models.EmailField(
                blank=True,
                help_text="Company contact email",
                max_length=254,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="company",
            name="staff_user_ids",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text="Breneo-api user IDs allowed to manage this company (list of strings)",
            ),
        ),
        migrations.AddField(
            model_name="company",
            name="industry",
            field=models.ForeignKey(
                blank=True,
                help_text="Industry classification",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="companies",
                to="jobs.industry",
            ),
        ),
    ]
