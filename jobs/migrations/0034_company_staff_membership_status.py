# Replace is_admin with status (pending | member | admin)

from django.db import migrations, models


def migrate_is_admin_to_status(apps, schema_editor):
    CompanyStaffMembership = apps.get_model("jobs", "CompanyStaffMembership")
    for row in CompanyStaffMembership.objects.all():
        row.status = "admin" if row.is_admin else "member"
        row.save(update_fields=["status"])


def promote_first_staff_without_admin(apps, schema_editor):
    CompanyStaffMembership = apps.get_model("jobs", "CompanyStaffMembership")
    seen_companies = set()
    for row in CompanyStaffMembership.objects.order_by("company_id", "id"):
        if row.company_id in seen_companies:
            continue
        seen_companies.add(row.company_id)
        if row.status != "admin":
            row.status = "admin"
            row.save(update_fields=["status"])


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("jobs", "0033_company_staff_membership_profile_admin"),
    ]

    operations = [
        migrations.AddField(
            model_name="companystaffmembership",
            name="status",
            field=models.CharField(
                choices=[
                    ("pending", "Pending"),
                    ("member", "Member"),
                    ("admin", "Admin"),
                ],
                db_index=True,
                default="member",
                help_text="pending = awaiting approval; member = staff; admin = can manage team",
                max_length=20,
            ),
        ),
        migrations.RunPython(migrate_is_admin_to_status, noop_reverse),
        migrations.RunPython(promote_first_staff_without_admin, noop_reverse),
        migrations.RemoveField(
            model_name="companystaffmembership",
            name="is_admin",
        ),
    ]
