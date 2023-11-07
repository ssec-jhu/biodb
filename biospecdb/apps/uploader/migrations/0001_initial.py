# Generated by Django 4.2.5 on 2023-11-10 22:42

import django.core.validators
from django.db import migrations, models
import django.db.models.deletion
import django.db.models.functions.text
import uploader.base_models
import uploader.models
import user.models
import uuid


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='FullPatientView',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ],
            options={
                'db_table': 'full_patient',
                'managed': False,
            },
            bases=(uploader.base_models.SqlView, models.Model),
        ),
        migrations.CreateModel(
            name='SymptomsView',
            fields=[
                ('disease', models.CharField(db_column='disease', max_length=128)),
                ('value_class', models.CharField(choices=[('BOOL', 'Bool'), ('STR', 'Str'), ('INT', 'Int'), ('FLOAT', 'Float')], default='BOOL', max_length=128)),
                ('days_symptomatic', models.IntegerField(blank=True, default=None, null=True, validators=[django.core.validators.MinValueValidator(0)], verbose_name='Days of Symptoms onset')),
                ('severity', models.IntegerField(blank=True, default=None, null=True, validators=[django.core.validators.MinValueValidator(0), django.core.validators.MaxValueValidator(10)])),
                ('disease_value', models.CharField(blank=True, default='', max_length=128, null=True)),
                ('visit_id', models.BigIntegerField(primary_key=True, serialize=False)),
            ],
            options={
                'db_table': 'v_symptoms',
                'managed': False,
            },
            bases=(uploader.base_models.SqlView, models.Model),
        ),
        migrations.CreateModel(
            name='VisitSymptomsView',
            fields=[
                ('visit_id', models.BigIntegerField(primary_key=True, serialize=False)),
            ],
            options={
                'db_table': 'v_visit_symptoms',
                'managed': False,
            },
            bases=(uploader.base_models.SqlView, models.Model),
        ),
        migrations.CreateModel(
            name='BioSample',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('sample_processing', models.CharField(blank=True, default='None', max_length=128, null=True, verbose_name='Sample Processing')),
                ('freezing_temp', models.FloatField(blank=True, null=True, verbose_name='Freezing Temperature')),
                ('thawing_time', models.IntegerField(blank=True, null=True, verbose_name='Thawing time')),
            ],
            options={
                'get_latest_by': 'updated_at',
            },
        ),
        migrations.CreateModel(
            name='BioSampleType',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('name', models.CharField(max_length=128, verbose_name='Sample Type')),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='Center',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, primary_key=True, serialize=False, unique=True)),
                ('name', models.CharField(max_length=128)),
                ('country', models.CharField(max_length=128, validators=[user.models.validate_country])),
            ],
            options={
                'abstract': False,
                'unique_together': {('name', 'country')},
            },
        ),
        migrations.CreateModel(
            name='Disease',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('name', models.CharField(max_length=128)),
                ('description', models.CharField(max_length=256)),
                ('alias', models.CharField(help_text='Alias column name for bulk data ingestion from .csv, etc.', max_length=128)),
                ('value_class', models.CharField(choices=[('BOOL', 'Bool'), ('STR', 'Str'), ('INT', 'Int'), ('FLOAT', 'Float')], default='BOOL', max_length=128)),
                ('center', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, to='uploader.center')),
            ],
            options={
                'get_latest_by': 'updated_at',
            },
        ),
        migrations.CreateModel(
            name='Instrument',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('spectrometer', models.CharField(max_length=128, verbose_name='Spectrometer')),
                ('atr_crystal', models.CharField(max_length=128, verbose_name='ATR Crystal')),
            ],
            options={
                'get_latest_by': 'updated_at',
                'unique_together': {('spectrometer', 'atr_crystal')},
            },
        ),
        migrations.CreateModel(
            name='Patient',
            fields=[
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('patient_id', models.UUIDField(default=uuid.uuid4, primary_key=True, serialize=False, unique=True, verbose_name='Patient ID')),
                ('gender', models.CharField(choices=[('X', 'Unspecified'), ('M', 'Male'), ('F', 'Female')], max_length=8, null=True, verbose_name='Gender (M/F)')),
                ('patient_cid', models.CharField(blank=True, help_text='Patient ID prescribed by the associated center', max_length=128, null=True)),
                ('center', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='uploader.center')),
            ],
            options={
                'get_latest_by': 'updated_at',
                'unique_together': {('patient_cid', 'center')},
            },
        ),
        migrations.CreateModel(
            name='QCAnnotator',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('name', models.CharField(max_length=128, unique=True)),
                ('fully_qualified_class_name', models.CharField(help_text="This must be the fully qualified Python name for an implementation of QCFilter, e.g.,'myProject.qc.myQCFilter'.", max_length=128, unique=True, validators=[uploader.models.validate_qc_annotator_import])),
                ('value_type', models.CharField(choices=[('BOOL', 'Bool'), ('STR', 'Str'), ('INT', 'Int'), ('FLOAT', 'Float')], default='BOOL', max_length=128)),
                ('description', models.CharField(blank=True, max_length=256, null=True)),
                ('default', models.BooleanField(default=True, help_text='If True it will apply to all spectral data samples.')),
            ],
            options={
                'get_latest_by': 'updated_at',
            },
        ),
        migrations.CreateModel(
            name='SpectraMeasurementType',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('name', models.CharField(max_length=128, verbose_name='Spectra Measurement')),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='Visit',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('patient_age', models.IntegerField(validators=[django.core.validators.MinValueValidator(0), django.core.validators.MaxValueValidator(150)], verbose_name='Age')),
                ('patient', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='visit', to='uploader.patient')),
                ('previous_visit', models.ForeignKey(blank=True, default=None, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='next_visit', to='uploader.visit')),
            ],
            options={
                'get_latest_by': 'updated_at',
            },
        ),
        migrations.CreateModel(
            name='UploadedFile',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('meta_data_file', models.FileField(help_text='File containing rows of all patient, symptom, and other meta data.', upload_to='raw_data/', validators=[django.core.validators.FileExtensionValidator(['csv', 'xlsx', 'json'])])),
                ('spectral_data_file', models.FileField(help_text='File containing rows of spectral intensities for the corresponding meta data file.', upload_to='raw_data/', validators=[django.core.validators.FileExtensionValidator(['csv', 'xlsx', 'json'])])),
                ('center', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='uploader.center')),
            ],
            options={
                'verbose_name': 'Bulk Data Upload',
                'get_latest_by': 'updated_at',
            },
        ),
        migrations.CreateModel(
            name='Symptom',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('days_symptomatic', models.IntegerField(blank=True, default=None, null=True, validators=[django.core.validators.MinValueValidator(0)], verbose_name='Days of Symptoms onset')),
                ('severity', models.IntegerField(blank=True, default=None, null=True, validators=[django.core.validators.MinValueValidator(0), django.core.validators.MaxValueValidator(10)])),
                ('disease_value', models.CharField(blank=True, default='', max_length=128, null=True)),
                ('disease', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='symptom', to='uploader.disease')),
                ('visit', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='symptom', to='uploader.visit')),
            ],
            options={
                'get_latest_by': 'updated_at',
            },
        ),
        migrations.CreateModel(
            name='SpectralData',
            fields=[
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('id', models.UUIDField(default=uuid.uuid4, primary_key=True, serialize=False, unique=True)),
                ('acquisition_time', models.IntegerField(blank=True, null=True, verbose_name='Acquisition time [s]')),
                ('n_coadditions', models.IntegerField(default=32, verbose_name='Number of coadditions')),
                ('resolution', models.IntegerField(blank=True, null=True, verbose_name='Resolution [cm-1]')),
                ('data', models.FileField(upload_to='spectral_data/', validators=[django.core.validators.FileExtensionValidator(['csv', 'xlsx', 'json'])], verbose_name='Spectral data file')),
                ('bio_sample', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='spectral_data', to='uploader.biosample')),
                ('instrument', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='spectral_data', to='uploader.instrument')),
                ('spectra_measurement', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='spectral_data', to='uploader.spectrameasurementtype', verbose_name='Spectra Measurement')),
            ],
            options={
                'verbose_name': 'Spectral Data',
                'verbose_name_plural': 'Spectral Data',
                'get_latest_by': 'updated_at',
            },
        ),
        migrations.AddField(
            model_name='biosample',
            name='sample_type',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='bio_sample', to='uploader.biosampletype', verbose_name='Sample Type'),
        ),
        migrations.AddField(
            model_name='biosample',
            name='visit',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='bio_sample', to='uploader.visit'),
        ),
        migrations.CreateModel(
            name='QCAnnotation',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('value', models.CharField(blank=True, max_length=128, null=True)),
                ('annotator', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='qc_annotation', to='uploader.qcannotator')),
                ('spectral_data', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='qc_annotation', to='uploader.spectraldata')),
            ],
            options={
                'get_latest_by': 'updated_at',
                'unique_together': {('annotator', 'spectral_data')},
            },
        ),
        migrations.AddConstraint(
            model_name='disease',
            constraint=models.UniqueConstraint(django.db.models.functions.text.Lower('name'), name='unique_disease_name'),
        ),
        migrations.AddConstraint(
            model_name='disease',
            constraint=models.UniqueConstraint(django.db.models.functions.text.Lower('alias'), name='unique_alias_name'),
        ),
    ]
