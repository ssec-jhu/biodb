# Generated by Django 4.2.11 on 2024-03-09 17:16

import catalog.models
import django.core.validators
from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('explorer', '0013_querylog_error_querylog_success'),
    ]

    operations = [
        migrations.CreateModel(
            name='Dataset',
            fields=[
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('id', models.UUIDField(default=uuid.uuid4, primary_key=True, serialize=False, unique=True, verbose_name='ID')),
                ('sql', models.TextField(blank=True, editable=False, verbose_name='SQL')),
                ('version', models.CharField(help_text='Version String, i.e., YYYY.N', max_length=32)),
                ('name', models.CharField(blank=True, help_text='If not provide the query title will be used', max_length=32)),
                ('description', models.TextField(blank=True, help_text='If not provide the query description will be used', max_length=256)),
                ('file', models.FileField(blank=True, editable=False, max_length=256, upload_to='datasets/')),
                ('app_version', models.CharField(blank=True, default=catalog.models.get_app_version, editable=False, help_text='App version used to create data product', max_length=32)),
                ('sha256', models.CharField(blank=True, editable=False, help_text='Checksum of downloadable file', max_length=64, validators=[django.core.validators.MinLengthValidator(64)], verbose_name='SHA-256')),
                ('n_rows', models.IntegerField(blank=True, editable=False, help_text='Number of data rows')),
                ('data_sha256', models.CharField(blank=True, editable=False, help_text='Checksum of data table (not including any array data files).', max_length=64, validators=[django.core.validators.MinLengthValidator(64)], verbose_name='Data SHA-256')),
                ('array_data_filenames', models.JSONField(blank=True, default=catalog.models.empty_list, editable=False, encoder=catalog.models.CustomDjangoJsonEncoder, help_text='List of array data filenames')),
                ('query', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='dataset', to='explorer.query')),
            ],
            options={
                'verbose_name': 'BSR dataset',
                'get_latest_by': 'updated_at',
                'unique_together': {('name', 'version')},
            },
        ),
    ]
