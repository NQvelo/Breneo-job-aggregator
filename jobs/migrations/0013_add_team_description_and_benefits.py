# Generated migration for adding team_description and benefits fields

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('jobs', '0012_add_responsibilities_and_qualification'),
    ]

    operations = [
        migrations.AddField(
            model_name='job',
            name='team_description',
            field=models.TextField(blank=True, help_text='Team description from job posting, if available', null=True),
        ),
        migrations.AddField(
            model_name='job',
            name='benefits',
            field=models.TextField(blank=True, help_text='Benefits section from job posting, if available', null=True),
        ),
    ]
