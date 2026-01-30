# Generated migration for removing team_description field

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("jobs", "0013_add_team_description_and_benefits"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="job",
            name="team_description",
        ),
    ]
