import interview_api.storage
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("interview_api", "0005_interview_job_fk"),
    ]

    operations = [
        migrations.AddField(
            model_name="interview",
            name="welcome_text",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="interview",
            name="welcome_audio",
            field=models.FileField(
                blank=True,
                storage=interview_api.storage.interview_audio_storage,
                upload_to="interview_welcome/",
            ),
        ),
    ]
