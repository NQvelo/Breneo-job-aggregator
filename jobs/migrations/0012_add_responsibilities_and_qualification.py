# Generated migration for adding responsibilities and qualifications fields

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('jobs', '0011_remove_job_company_logo_and_location_country'),
    ]

    operations = [
        migrations.AddField(
            model_name='job',
            name='responsibilities',
            field=models.TextField(blank=True, help_text='Extracted responsibilities section from job description', null=True),
        ),
        migrations.AddField(
            model_name='job',
            name='qualifications',
            field=models.TextField(blank=True, help_text='Extracted qualifications/requirements section from job description', null=True),
        ),
    ]
