from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("jobs", "0035_job_applicant_cv_view"),
    ]

    operations = [
        migrations.AddField(
            model_name="jobapplicantcvview",
            name="applicant_acknowledged_at",
            field=models.DateTimeField(
                blank=True,
                help_text="When the applicant acknowledged/dismissed the view notification",
                null=True,
            ),
        ),
    ]
