import interview_api.storage
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("interview_api", "0007_prepared_role_questions"),
    ]

    operations = [
        migrations.CreateModel(
            name="PreparedSpeech",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("text_hash", models.CharField(max_length=64, unique=True)),
                (
                    "audio",
                    models.FileField(
                        blank=True,
                        storage=interview_api.storage.interview_audio_storage,
                        upload_to="interview_prepared/",
                    ),
                ),
            ],
        ),
    ]
