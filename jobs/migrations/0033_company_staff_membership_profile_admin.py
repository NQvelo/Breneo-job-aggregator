# Generated manually for company staff profile + admin fields

from django.db import migrations, models


def promote_first_staff_to_admin(apps, schema_editor):
    CompanyStaffMembership = apps.get_model("jobs", "CompanyStaffMembership")
    seen_companies = set()
    for row in CompanyStaffMembership.objects.order_by("company_id", "id"):
        if row.company_id in seen_companies:
            continue
        seen_companies.add(row.company_id)
        if not row.is_admin:
            row.is_admin = True
            row.save(update_fields=["is_admin"])


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("jobs", "0032_job_application_user_profile"),
    ]

    operations = [
        migrations.AddField(
            model_name="companystaffmembership",
            name="external_user_email",
            field=models.EmailField(
                blank=True,
                default="",
                help_text="Staff email from breneo-api / BFF at membership time",
                max_length=254,
            ),
        ),
        migrations.AddField(
            model_name="companystaffmembership",
            name="external_user_name",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Staff first name at membership time",
                max_length=255,
            ),
        ),
        migrations.AddField(
            model_name="companystaffmembership",
            name="external_user_surname",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Staff last name at membership time",
                max_length=255,
            ),
        ),
        migrations.AddField(
            model_name="companystaffmembership",
            name="is_admin",
            field=models.BooleanField(
                default=False,
                help_text="Company admin: can remove other staff for this company",
            ),
        ),
        migrations.RunPython(promote_first_staff_to_admin, noop_reverse),
    ]
