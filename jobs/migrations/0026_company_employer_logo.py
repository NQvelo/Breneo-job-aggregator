from cloudinary_storage.storage import MediaCloudinaryStorage
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("jobs", "0025_company_employer_created_flag"),
    ]

    operations = [
        migrations.AddField(
            model_name="company",
            name="employer_logo",
            field=models.ImageField(
                blank=True,
                help_text="Uploaded employer profile logo (multipart field name: employer_logo)",
                null=True,
                storage=MediaCloudinaryStorage(),
                upload_to="employer_logos/",
            ),
        ),
    ]
