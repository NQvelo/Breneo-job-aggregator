from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('jobs', '0039_job_deadline'),
    ]

    operations = [
        migrations.AddField(
            model_name='job',
            name='location_region',
            field=models.CharField(
                blank=True,
                db_index=True,
                help_text="State or admin region parsed from location (U.S. state of Georgia is 'Georgia' with country USA)",
                max_length=100,
                null=True,
            ),
        ),
    ]
