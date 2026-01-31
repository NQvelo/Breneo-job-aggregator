# Generated migration: Add tech_stack_candidates for catalog expansion

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("jobs", "0016_add_matching_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="job",
            name="tech_stack_candidates",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text="Tech-like tokens not in catalog, for review/expansion",
            ),
        ),
    ]
