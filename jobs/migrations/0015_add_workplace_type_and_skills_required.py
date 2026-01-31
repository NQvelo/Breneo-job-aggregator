# Generated migration for adding workplace_type and skills_required

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("jobs", "0014_remove_job_team_description"),
    ]

    operations = [
        migrations.AddField(
            model_name="job",
            name="workplace_type",
            field=models.CharField(
                blank=True,
                help_text="Workplace type: Remote, Hybrid, or On-site",
                max_length=50,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="job",
            name="skills_required",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text="List of required skills extracted from job posting",
            ),
        ),
    ]
