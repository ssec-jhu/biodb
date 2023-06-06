from django.db import models

# Changes here need to be migrated, committed, and activated.
# See https://docs.djangoproject.com/en/4.2/intro/tutorial02/#activating-models
# python manage.py makemigrations uploader
# git add biospecdb/apps/uploader/migrations
# git commit -asm"Update uploader model(s)"
# python manage.py migrate
# python manage.py sqlmigrate uploader <migration_version>

class UploadedFile(models.Model):
    file = models.FileField(upload_to='./biospecdb/apps/uploader/uploads/')
    uploaded_at = models.DateTimeField(auto_now_add=True)
    
class BioSample(models.Model):
    # Sample meta.
    sample_type = models.CharField(max_length=128)
    sample_processing = models.CharField(max_length=128)
    freezing_time = models.IntegerField(default=0)  # models.DateTimeField?
    thawing_time = models.IntegerField(default=0)  # models.DateTimeField?

    # Spectrometer meta.
    spectra_measurment = models.CharField(max_length=128)
    spectrometer = models.CharField(max_length=128)
    atr_crystal = models.CharField(max_length=128)
    acquisition_time = models.IntegerField(default=0)  # models.DateTimeField?
    n_coadditions = models.IntegerField(default=0)
    resolution = models.IntegerField(default=0)

    # Spectral data.
    wavelengths = models.IntegerField(default=0)
    intensities = models.IntegerField(default=0)


class Patient(models.Model):
    patient_id = models.IntegerField(default=0, unique=True, primary_key=True)

    # Meta
    gender = models.CharField(max_length=1)
    age = models.IntegerField(default=0)
    days_of_symptoms = models.IntegerField(default=0)

    # Symptoms/Diseases
    fever = models.BooleanField(default=False)
    dyspnoea = models.BooleanField(default=False)
    oxygen_saturation_lt_95 = models.BooleanField(default=False)
    cough = models.BooleanField(default=False)
    coryza = models.BooleanField(default=False)
    odinophagy = models.BooleanField(default=False)
    diarrhea = models.BooleanField(default=False)
    nausea = models.BooleanField(default=False)
    headache = models.BooleanField(default=False)
    weakness = models.BooleanField(default=False)
    anosmia = models.BooleanField(default=False)
    myalgia = models.BooleanField(default=False)
    no_appetite = models.BooleanField(default=False)
    vomiting = models.BooleanField(default=False)
    suspicious_contact = models.BooleanField(default=False)
    chronic_pulmonary_inc_asthma = models.BooleanField(default=False)
    cardiovascular_disease_inc_hypertension = models.BooleanField(default=False)
    diabetes = models.BooleanField(default=False)
    chronic_or_neuromuscular_neurological_disease = models.BooleanField(default=False)

    # Sample meta data & spectral data.
    data = models.ForeignKey(BioSample, on_delete=models.CASCADE)
