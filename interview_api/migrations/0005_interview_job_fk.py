from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("jobs", "0036_job_applicant_cv_view_acknowledged"),
        ("interview_api", "0004_multi_question_and_question_audio"),
    ]

    operations = [
        migrations.AddField(
            model_name="interview",
            name="job",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="interviews",
                to="jobs.job",
            ),
        ),
    ]
