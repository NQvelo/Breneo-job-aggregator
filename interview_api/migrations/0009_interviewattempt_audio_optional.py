import interview_api.storage
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("interview_api", "0008_preparedspeech"),
    ]

    operations = [
        migrations.AlterField(
            model_name="interviewattempt",
            name="audio_file",
            field=models.FileField(
                blank=True,
                storage=interview_api.storage.interview_audio_storage,
                upload_to="interview_records/",
            ),
        ),
    ]
