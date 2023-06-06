# Generated by Django 4.2.1 on 2023-05-31 02:01

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("uploader", "0002_rename_biosampledata_biosample_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="UploadedFile",
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
                    "file",
                    models.FileField(upload_to="./biospecdb/apps/uploader/uploads/"),
                ),
                ("uploaded_at", models.DateTimeField(auto_now_add=True)),
            ],
        ),
    ]
