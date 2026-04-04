# Generated manually for normalized breneo user ↔ company links.

from django.db import migrations, models
import django.db.models.deletion


def copy_staff_json_to_memberships(apps, schema_editor):
    Company = apps.get_model("jobs", "Company")
    CompanyStaffMembership = apps.get_model("jobs", "CompanyStaffMembership")
    for company in Company.objects.all().iterator():
        raw = company.staff_user_ids
        if not isinstance(raw, list):
            continue
        for uid in raw:
            uid = str(uid).strip()
            if uid:
                CompanyStaffMembership.objects.get_or_create(
                    company=company, external_user_id=uid
                )


def noop_reverse(apps, schema_editor):
    CompanyStaffMembership = apps.get_model("jobs", "CompanyStaffMembership")
    CompanyStaffMembership.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ("jobs", "0021_company_industries_m2m_and_trim_industry"),
    ]

    operations = [
        migrations.CreateModel(
            name="CompanyStaffMembership",
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
                (
                    "external_user_id",
                    models.CharField(
                        db_index=True,
                        help_text="User id from breneo-api (string)",
                        max_length=255,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "company",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="staff_memberships",
                        to="jobs.company",
                    ),
                ),
            ],
            options={
                "ordering": ["company_id", "id"],
            },
        ),
        migrations.AddConstraint(
            model_name="companystaffmembership",
            constraint=models.UniqueConstraint(
                fields=("company", "external_user_id"),
                name="uniq_company_staff_external_user",
            ),
        ),
        migrations.RunPython(copy_staff_json_to_memberships, noop_reverse),
    ]
