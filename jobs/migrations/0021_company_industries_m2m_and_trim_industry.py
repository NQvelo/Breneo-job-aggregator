from django.db import migrations, models


def copy_industry_fk_to_m2m(apps, schema_editor):
    Company = apps.get_model("jobs", "Company")
    for row in Company.objects.exclude(industry_id=None).iterator():
        # M2M .add accepts primary key
        row.industries.add(row.industry_id)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("jobs", "0020_industry_and_company_employer_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="company",
            name="industries",
            field=models.ManyToManyField(
                blank=True,
                help_text="One or more industries (selectable)",
                related_name="companies",
                to="jobs.industry",
            ),
        ),
        migrations.RunPython(copy_industry_fk_to_m2m, noop_reverse),
        migrations.RemoveField(
            model_name="company",
            name="industry",
        ),
        migrations.RemoveField(
            model_name="industry",
            name="description",
        ),
        migrations.RemoveField(
            model_name="industry",
            name="slug",
        ),
    ]
