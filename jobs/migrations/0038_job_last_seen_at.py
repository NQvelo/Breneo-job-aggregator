from django.db import migrations, models
from django.db.models import F


def backfill_last_seen_at(apps, schema_editor):
    Job = apps.get_model("jobs", "Job")
    Job.objects.exclude(platform="employer").update(last_seen_at=F("fetched_at"))


class Migration(migrations.Migration):

    dependencies = [
        ('jobs', '0037_job_apply_email'),
    ]

    operations = [
        migrations.AddField(
            model_name='job',
            name='last_seen_at',
            field=models.DateTimeField(blank=True, help_text='Last time fetch_jobs saw this job in its source feed (null for employer jobs)', null=True),
        ),
        migrations.RunPython(backfill_last_seen_at, migrations.RunPython.noop),
    ]
