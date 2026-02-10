from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("jobs", "0017_add_tech_stack_candidates"),
    ]

    operations = [
        migrations.AddField(
            model_name="job",
            name="industry_tags",
            field=models.TextField(
                blank=True,
                null=True,
                db_column="industryTags",
                help_text=(
                    "Canonical industry tags, comma-separated, lowercase, "
                    "deduplicated, sorted alphabetically"
                ),
            ),
        ),
    ]

