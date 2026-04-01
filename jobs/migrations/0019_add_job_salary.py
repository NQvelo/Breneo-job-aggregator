from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("jobs", "0018_add_industry_tags_field"),
    ]

    operations = [
        migrations.AddField(
            model_name="job",
            name="salary",
            field=models.CharField(
                blank=True,
                help_text="Salary or compensation summary (as entered or normalized)",
                max_length=500,
                null=True,
            ),
        ),
    ]
