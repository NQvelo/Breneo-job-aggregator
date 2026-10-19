from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('jobs', '0038_job_last_seen_at'),
    ]

    operations = [
        migrations.AddField(
            model_name='job',
            name='deadline',
            field=models.DateTimeField(blank=True, db_index=True, help_text='Application deadline from the source; the job stays visible until the day after this date (Georgia time)', null=True),
        ),
    ]
