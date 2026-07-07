# Generated manually for multi-question interview flow

import interview_api.storage
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("interview_api", "0003_alter_interviewattempt_audio_storage"),
    ]

    operations = [
        migrations.AddField(
            model_name="interviewquestion",
            name="order",
            field=models.PositiveSmallIntegerField(default=1),
        ),
        migrations.AddField(
            model_name="interviewquestion",
            name="question_audio",
            field=models.FileField(
                blank=True,
                storage=interview_api.storage.interview_audio_storage,
                upload_to="interview_questions/",
            ),
        ),
        migrations.AlterModelOptions(
            name="interviewquestion",
            options={"ordering": ["order"]},
        ),
        migrations.AddConstraint(
            model_name="interviewquestion",
            constraint=models.UniqueConstraint(
                fields=("interview", "order"),
                name="interview_api_unique_question_order",
            ),
        ),
    ]
