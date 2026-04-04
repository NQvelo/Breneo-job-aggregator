from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("jobs", "0022_company_staff_membership"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="company",
            name="staff_user_ids",
        ),
    ]
