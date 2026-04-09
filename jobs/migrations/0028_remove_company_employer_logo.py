from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("jobs", "0027_unapplied_marker"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="company",
            name="employer_logo",
        ),
    ]

