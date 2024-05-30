import os
from pathlib import Path
import shutil
from uuid import uuid4

from django.conf import settings
from django.core.exceptions import ValidationError
import django.core.files
from django.core.files.base import ContentFile
from django.db.utils import IntegrityError
import pytest

import uploader.io
from uploader.models import BioSample, BioSampleType, Observable, Instrument, Patient, ArrayData, Observation,\
    Visit, UploadedFile, get_center, Center, ArrayMeasurementType
from uploader.loaddata import save_data_to_db
from user.models import Center as UserCenter
from uploader.models import Center as UploaderCenter
import biodb.util
from uploader.tests.conftest import bulk_upload, DATA_PATH


@pytest.mark.django_db(databases=["default", "bsr"])
class TestPatient:
    def test_creation(self, center):
        Patient(center=center).full_clean()

    def test_db_creation(self, center):
        Patient.objects.create(center=center).full_clean()
        Patient.objects.create(center=center).full_clean()
        Patient.objects.create(center=center).full_clean()

        assert Patient.objects.count() == 3

        Patient.objects.create(center=center).full_clean()
        assert Patient.objects.count() == 4

        qs = Patient.objects.filter(center=center)
        assert qs[0].patient_id != qs[1].patient_id

    def test_short_name(self, center):
        patient = Patient(center=center)
        patient.full_clean()
        assert patient.short_id() in str(patient)

    def test_fixture_data(self, db, patients):
        assert Patient.objects.count() == 3
        assert Patient.objects.get(pk="437de0d7-6618-4445-bab2-03822310b0ef")

    def test_editable_patient_id(self, center):
        patient_id = uuid4()
        Patient.objects.create(patient_id=patient_id, center=center)
        assert Patient.objects.get(pk=patient_id)

    def test_center_validation(self, centers):
        center = UploaderCenter.objects.get(name="jhu")
        assert UserCenter.objects.filter(pk=center.pk).exists()
        assert UploaderCenter.objects.filter(pk=center.pk).exists()

        # OK.
        patient_id = uuid4()
        patient = Patient(patient_id=patient_id, center=center)
        patient.full_clean()

        # Not OK.
        patient_id = uuid4()
        with pytest.raises(ValueError, match="Cannot assign"):
            patient = Patient(patient_id=patient_id,
                              center=UserCenter.objects.get(name="jhu"))

    def test_unique_cid_center_id(self, centers):
        center = UploaderCenter.objects.get(name="jhu")
        cid = uuid4()
        Patient.objects.create(patient_id=uuid4(),
                               center=center,
                               patient_cid=cid)
        # OK.
        Patient.objects.create(patient_id=uuid4(),
                               center=center,
                               patient_cid=uuid4())

        # OK.
        Patient.objects.create(patient_id=uuid4(),
                               center=UploaderCenter.objects.get(name="Imperial College London"),
                               patient_cid=cid)

        # Not OK.
        with pytest.raises(IntegrityError, match="UNIQUE constraint failed:"):
            Patient.objects.create(patient_id=uuid4(),
                                   center=center,
                                   patient_cid=cid)

    def test_pi_cid_validation(self, centers):
        id = uuid4()
        patient = Patient(patient_id=id,
                          patient_cid=id,
                          center=Center.objects.get(name="jhu"))
        with pytest.raises(ValidationError, match="Patient ID and patient CID cannot be the same"):
            patient.full_clean()


@pytest.mark.django_db(databases=["default", "bsr"])
class TestVisit:
    def test_visit_number(self, db, visits):
        assert Visit.objects.get(pk=1).visit_number == 1
        assert Visit.objects.get(pk=3).visit_number == 2

    def test_walk(self, db, visits):
        v1 = Visit.objects.get(pk=1)
        v2 = Visit.objects.get(pk=3)
        assert v1.patient.pk == v2.patient.pk

    def test_previous_visit_same_patient_validation(self, db, visits):
        visit = Visit.objects.get(pk=2)
        visit.previous_visit = Visit.objects.get(pk=1)
        with pytest.raises(ValidationError):
            visit.full_clean()

    @pytest.mark.auto_find_previous_visit(False)
    def test_disabled_auto_find_previous_visit(self, visits):
        visit = Visit.objects.get(pk=4)
        assert not visit.previous_visit
        visit.full_clean()
        assert not visit.previous_visit

    @pytest.mark.auto_find_previous_visit(True)
    def test_auto_find_previous_visit(self, visits):
        visit = Visit.objects.get(pk=4)
        assert not visit.previous_visit
        visit.full_clean()
        previous_visit = Visit.objects.get(pk=2)
        assert visit.previous_visit == previous_visit

        new_visit = Visit.objects.get(pk=5)
        new_visit.full_clean()
        assert new_visit.previous_visit == visit

    @pytest.mark.auto_find_previous_visit(True)
    def test_ambiguous_previous_visit(self, visits):
        assert Visit.objects.get(pk=5).created_at == Visit.objects.get(pk=6).created_at
        assert Visit.objects.get(pk=7).created_at > Visit.objects.get(pk=5).created_at
        with pytest.raises(ValidationError, match="Auto previous visit ambiguity:"):
            Visit.objects.get(pk=7).full_clean()

    @pytest.mark.auto_find_previous_visit(True)
    def test_previous_visit_update(self, visits):
        visit = Visit.objects.get(pk=4)
        visit.full_clean()
        assert visit.previous_visit == Visit.objects.get(pk=2)

        visit.full_clean()
        assert visit.previous_visit == Visit.objects.get(pk=2)

    @pytest.mark.parametrize(tuple(),
                             [pytest.param(marks=pytest.mark.auto_find_previous_visit(False)),
                              pytest.param(marks=pytest.mark.auto_find_previous_visit(True))])
    def test_previous_visit_patient_age_validation(self, db, visits, observables):
        previous_visit = Visit.objects.get(pk=1)
        age = 10
        patient_age = Observation.objects.create(visit=previous_visit,
                                                 observable=Observable.objects.get(name="patient_age"),
                                                 observable_value=age)
        previous_visit.observation.add(patient_age, bulk=False)

        visit = Visit.objects.create(patient=previous_visit.patient, previous_visit=previous_visit)
        patient_age = Observation.objects.create(visit=visit,
                                                 observable=Observable.objects.get(name="patient_age"),
                                                 observable_value=age - 1)
        visit.observation.add(patient_age, bulk=False)

        with pytest.raises(ValidationError, match="Previous visit must NOT be older than this one"):
            visit.full_clean()

    def test_circular_previous_visit(self, db, visits):
        visit = Visit.objects.get(pk=1)
        visit.previous_visit = visit
        with pytest.raises(ValidationError, match="Previous visit cannot not be this current visit"):
            visit.full_clean()

    def test_days_of_symptoms_onset(self, mock_data_from_files):
        week_long_observations = Visit.objects.filter(days_observed=7)
        assert week_long_observations.count() == 1
        assert week_long_observations[0].days_observed == 7
        null_days = Visit.objects.filter(days_observed=None).count()
        assert null_days == 1
        assert null_days < Visit.objects.count()


@pytest.mark.django_db(databases=["default", "bsr"])
class TestObservable:
    def test_fixture_data(self, db, observables):
        observable = Observable.objects.get(pk=1)
        assert observable.name == "Ct_gene_N"
        assert observable.value_class == Observable.Types.FLOAT

    def test_name_uniqueness(self, db):
        Observable.objects.create(name="A", description="blah", alias="a", category=Observable.Category.COMORBIDITY)
        with pytest.raises(IntegrityError, match="unique_observable_name"):
            Observable.objects.create(name="a", description="blah", alias="b", category=Observable.Category.COMORBIDITY)

    def test_alias_uniqueness(self, db):
        Observable.objects.create(name="A", description="blah", alias="a", category=Observable.Category.COMORBIDITY)
        with pytest.raises(IntegrityError, match="unique_alias_name"):
            Observable.objects.create(name="b", description="blah", alias="A", category=Observable.Category.COMORBIDITY)

    def test_list_choices(self):
        choices = "this, or, that"
        assert Observable.list_choices(choices) == ["THIS", "OR", "THAT"]

    def test_djangofy_choices(self):
        choices = "this, or, that"
        assert Observable.djangofy_choices(choices) == [("THIS", "THIS"),
                                                        ("OR", "OR"),
                                                        ("THAT", "THAT")]

    def test_validator_import_validation(self):
        Observable(name="A",
                   description="blah",
                   alias="a",
                   category=Observable.Category.COMORBIDITY,
                   validator="django.core.validators.validate_email").full_clean()

        with pytest.raises(ValidationError, match="cannot be imported"):
            Observable(name="A",
                       description="blah",
                       alias="a",
                       category=Observable.Category.COMORBIDITY,
                       validator="some.random.method").full_clean()

    def test_choices_str_validation(self):
        Observable(name="A",
                   description="blah",
                   alias="a",
                   category=Observable.Category.COMORBIDITY,
                   value_class="STR",
                   value_choices="this,or,that").full_clean()

        with pytest.raises(ValidationError, match="Observable choices are only permitted of STR value_class"):
            Observable(name="A",
                       description="blah",
                       alias="a",
                       category=Observable.Category.COMORBIDITY,
                       value_class="BOOL",
                       value_choices="this,or,that").full_clean()


@pytest.mark.django_db(databases=["default", "bsr"])
class TestInstrument:
    def test_fixture_data(self, db, instruments):
        Instrument.objects.get(pk="4205d8ac-90c1-4529-90b2-6751f665c403")

    def test_new(self, db, instruments):
        Instrument.objects.create()
        assert Instrument.objects.count() == 2


@pytest.mark.django_db(databases=["default", "bsr"])
class TestObservation:
    def test_observable_value_validation(self, db, observables, visits):
        observation = Observation.objects.create(visit=Visit.objects.get(pk=1),
                                         observable=Observable.objects.get(name="Ct_gene_N"),
                                         days_observed=7,
                                         observable_value="strings can't cast to floats")
        with pytest.raises(ValidationError):
            observation.full_clean()

    @pytest.mark.parametrize("value", (True, False))
    def test_observable_value_bool_cast(self, db, observables, visits, value):
        observation = Observation.objects.create(visit=Visit.objects.get(pk=1),
                                         observable=Observable.objects.get(name="fever"),
                                         days_observed=7,
                                         observable_value=str(value))
        observation.full_clean()
        assert observation.observable_value is value

    def test_center_validation(self, centers):
        center = Center.objects.get(name="jhu")
        patient = Patient.objects.create(center=center)
        visit = Visit.objects.create(patient=patient)

        # OK.
        observable = Observable.objects.create(name="snuffles",
                                               alias="snuffles",
                                               category=Observable.Category.SYMPTOM)
        observable.center.set([center])
        Observation(visit=visit, observable=observable).full_clean()

        # OK.
        observable = Observable.objects.create(name="extra_snuffles",
                                               alias="extra snuffles",
                                               category=Observable.Category.SYMPTOM)
        Observation(visit=visit, observable=observable).full_clean()

        # Not OK.
        observable = Observable.objects.create(name="even_more_snuffles",
                                               alias="even more snuffles",
                                               category=Observable.Category.SYMPTOM)
        observable.center.set([Center.objects.get(name="Imperial College London")])
        with pytest.raises(ValidationError, match="Patient observation.observable must belong to patient's center"):
            Observation(visit=visit, observable=observable).full_clean()

    def test_observable_choices(self, observables, visits):
        Observation(visit=Visit.objects.last(),
                    observable=Observable.objects.get(name="gender"),
                    observable_value="non-binary").full_clean()

        with pytest.raises(ValidationError, match="Value must be one of"):
            Observation(visit=Visit.objects.last(),
                        observable=Observable.objects.get(name="gender"),
                        observable_value="blah-blah").full_clean()

    def test_observable_validator(self, visits):
        observable = Observable.objects.create(name="A",
                                               description="blah",
                                               alias="a",
                                               category=Observable.Category.COMORBIDITY,
                                               value_class="STR",
                                               validator="django.core.validators.validate_email")

        Observation(visit=Visit.objects.last(),
                    observable=observable,
                    observable_value="rando@gmail.com").full_clean()

        with pytest.raises(ValidationError, match="Enter a valid email address"):
            Observation(visit=Visit.objects.last(),
                        observable=observable,
                        observable_value="blahblah").full_clean()


@pytest.mark.django_db(databases=["default", "bsr"])
class TestBioSample:
    ...


@pytest.mark.django_db(databases=["default", "bsr"])
class TestArrayData:
    def test_files_added(self, mock_data_from_files):
        n_patients = 10
        assert ArrayData.objects.count() == n_patients
        for obj in ArrayData.objects.all():
            assert Path(obj.data.name).exists()

    def test_no_file_validation(self, db):
        """ Test that a validation error is raised rather than any other python exception which would indicate a bug.
        """
        data = ArrayData()
        with pytest.raises(ValidationError):
            data.full_clean()

    def test_temp_files_deleted(self, mock_data_from_files):
        n_patients = 10
        assert ArrayData.objects.count() == n_patients
        filename = Path(ArrayData.objects.all()[0].data.name)
        assert filename.parent.exists()
        assert filename.parent.is_dir()
        assert not list(filename.parent.glob(f"{uploader.io.TEMP_FILENAME_PREFIX}*"))

    def test_no_duplicate_data_files(self, mock_data_from_files):
        n_patients = 10
        assert ArrayData.objects.count() == n_patients
        filename = Path(ArrayData.objects.all()[0].data.name)
        assert filename.parent.exists()
        assert filename.parent.is_dir()
        assert len(list(filename.parent.glob('*'))) == n_patients

    @pytest.mark.skip("Unimplemented See #141")
    def test_all_files_deleted_upon_transaction_failure(self):
        # I'm not sure how to mock this...
        ...

    @pytest.mark.parametrize("ext", uploader.io.FileFormats.list())
    def test_clean(self, centers, instruments, ext, bio_sample_types, spectra_measurement_types):
        data_file = (DATA_PATH/"sample").with_suffix(ext)
        data = uploader.io.read_array_data(data_file)

        patient = Patient.objects.create(patient_id=data.patient_id,
                                         center=Center.objects.get(name="jhu"))
        visit = patient.visit.create()
        bio_sample = visit.bio_sample.create(sample_type=BioSampleType.objects.get(name="pharyngeal swab"))

        array_data = ArrayData(instrument=Instrument.objects.get(pk="4205d8ac-90c1-4529-90b2-6751f665c403"),
                                     bio_sample=bio_sample,
                                     data=ContentFile(data_file.read_bytes(), name=data_file),
                                     measurement_type=ArrayMeasurementType.objects.get(name="atr-ftir"))
        array_data.full_clean()
        array_data.save()

        assert Path(array_data.data.name).suffix == uploader.io.FileFormats.JSONL
        cleaned_data = array_data.get_array_data()
        assert cleaned_data == data

    def test_deletion(self, mock_data_from_files):
        array_data = ArrayData.objects.all()
        for item in array_data:
            assert ArrayData.data.field.storage.exists(item.data.name)
            item.delete()
            assert not ArrayData.data.field.storage.exists(item.data.name)
        assert not ArrayData.objects.count()


@pytest.mark.django_db(databases=["default", "bsr"])
class TestUploadedFile:
    @pytest.mark.parametrize("file_ext", UploadedFile.FileFormats.list())
    def test_upload_without_error(self,
                                  db,
                                  observables,
                                  instruments,
                                  file_ext,
                                  center,
                                  bio_sample_types,
                                  spectra_measurement_types):
        meta_data_path = (DATA_PATH/"meta_data").with_suffix(file_ext)
        array_file_path = (DATA_PATH / "array_data").with_suffix(file_ext)
        with meta_data_path.open(mode="rb") as meta_data, array_file_path.open(mode="rb") as array_data:
            data_upload = UploadedFile(meta_data_file=django.core.files.File(meta_data,
                                                                             name=meta_data_path.name),
                                       array_data_file=django.core.files.File(array_data,
                                                                                 name=array_file_path.name),
                                       center=center)
            data_upload.clean()
            data_upload.save()

    def test_mock_data_from_files_fixture(self, mock_data_from_files):
        n_patients = 10
        assert UploadedFile.objects.count() == 1
        assert Patient.objects.count() == n_patients
        assert Visit.objects.count() == n_patients
        assert BioSample.objects.count() == n_patients
        assert ArrayData.objects.count() == n_patients

    def test_center(self, mock_data_from_files):
        n_patients = Patient.objects.count()
        assert n_patients == 10
        center = Center.objects.get(name="jhu")
        assert n_patients == Patient.objects.filter(center=center).count()
        assert not Patient.objects.filter(center=None)

    def test_mock_data_fixture(self, mock_data):
        n_patients = 10
        assert Patient.objects.count() == n_patients
        assert Visit.objects.count() == n_patients
        assert BioSample.objects.count() == n_patients
        assert ArrayData.objects.count() == n_patients

    def test_number_observations(self,
                                 db,
                                 observables,
                                 instruments,
                                 center,
                                 bio_sample_types,
                                 spectra_measurement_types):
        """ The total number of observations := N_patients * N_observables. """
        assert Patient.objects.count() == 0  # Assert empty.

        save_data_to_db(DATA_PATH / "meta_data.csv",
                        DATA_PATH / "array_data.csv",
                        center=center)

        n_patients = Patient.objects.count()
        n_observables = Observable.objects.count()
        n_observations = Observation.objects.count()

        # Assert not empty.
        assert n_patients > 0
        assert n_observables > 0
        assert n_observations > 0

        # When Covid_RT_qPCR is negative both Ct_gene_N & Ct_gene_ORF1ab observations will be null and omitted.
        # This must be accounted for in the total.
        n_empty_covid_observations = Observation.objects.filter(observable__name="Covid_RT_qPCR")\
            .filter(observable_value="Negative").count()
        assert n_observations == n_patients * n_observables - n_empty_covid_observations * 2

    @pytest.mark.parametrize("file_ext", UploadedFile.FileFormats.list())
    def test_patient_ids(self, mock_data_from_files, file_ext):
        meta_data_path = (DATA_PATH / "meta_data").with_suffix(file_ext)
        df = uploader.io.read_meta_data(meta_data_path)

        all_patients = Patient.objects.all()

        assert all_patients.count() == len(df)
        for index in df.index:
            assert all_patients.get(**{settings.BULK_UPLOAD_INDEX_COLUMN_NAME: index})

    @pytest.mark.parametrize("file_ext", UploadedFile.FileFormats.list())
    def test_index_match_validation(self, db, observables, instruments, file_ext, tmp_path):
        meta_data_path = (DATA_PATH / "meta_data").with_suffix(file_ext)

        biodb.util.mock_bulk_array_data(path=tmp_path)
        array_file_path = tmp_path / "array_data.csv"
        with meta_data_path.open(mode="rb") as meta_data, array_file_path.open(mode="rb") as array_data:
            data_upload = UploadedFile(meta_data_file=django.core.files.File(meta_data,
                                                                             name=meta_data_path.name),
                                       array_data_file=django.core.files.File(array_data,
                                                                                 name=array_file_path.name))
            with pytest.raises(ValidationError, match="Patient index mismatch."):
                data_upload.clean()

    def test_re_upload(self, django_db_blocker, observables, instruments, mock_data_from_files):
        n_patients = 10
        assert UploadedFile.objects.count() == 1
        assert Patient.objects.count() == n_patients
        assert Visit.objects.count() == n_patients

        with django_db_blocker.unblock():
            bulk_upload()

        assert UploadedFile.objects.count() == 2
        assert Patient.objects.count() == n_patients
        assert Visit.objects.count() == n_patients * 2

    def test_upload_on_cid(self, django_db_blocker, observables, instruments, mock_data_from_files):
        if settings.BULK_UPLOAD_INDEX_COLUMN_NAME != "patient_id":
            pytest.skip("Test not applicable.")

        n_patients = 10
        assert UploadedFile.objects.count() == 1
        assert Patient.objects.count() == n_patients
        assert Visit.objects.count() == n_patients

        # copy patients but switch pid -> cid.
        new_patient_list = []
        old_pids = []
        for patient in Patient.objects.select_related("center").all():
            old_pids.append(patient.patient_id)
            new_patient_list.append(Patient(patient_cid=patient.patient_id,
                                            center=patient.center))
            patient.delete()

        # Check old patients successfully deleted.
        assert Patient.objects.count() == 0
        assert Visit.objects.count() == 0

        for new_patient in new_patient_list:
            new_patient.full_clean()
            new_patient.save()
            # Check new patients definitely aren't the old ones.
            assert new_patient.patient_id not in old_pids

        assert Patient.objects.count() == n_patients
        assert Visit.objects.count() == 0

        # Re-ingest data.
        bulk_upload()

        assert UploadedFile.objects.count() == 2
        # If bulk_upload failed to detect the existing patients by CID, new patients would have been created instead
        # and Patient.objects.count() == n_patients * 2.
        assert Patient.objects.count() == n_patients
        assert Visit.objects.count() == n_patients

    def test_deletion(self, mock_data_from_files):
        bulk_upload = UploadedFile.objects.all()[0]
        assert os.path.exists(bulk_upload.meta_data_file.name)
        assert os.path.exists(bulk_upload.array_data_file.name)
        bulk_upload.delete()
        assert not UploadedFile.objects.count()
        assert not os.path.exists(bulk_upload.meta_data_file.name)
        assert not os.path.exists(bulk_upload.array_data_file.name)

    def test_bad_ext(self,
                     db,
                     tmp_path,
                     observables,
                     instruments,
                     center,
                     bio_sample_types,
                     spectra_measurement_types):
        meta_data_path = (DATA_PATH/"meta_data").with_suffix(UploadedFile.FileFormats.CSV)
        array_file_path = (DATA_PATH / "array_data").with_suffix(UploadedFile.FileFormats.CSV)

        new_meta_data_path = tmp_path / meta_data_path.with_suffix(".blah")
        new_array_file_path = tmp_path / array_file_path.with_suffix(".blah")

        shutil.copyfile(meta_data_path, new_meta_data_path)
        shutil.copyfile(array_file_path, new_array_file_path)

        with new_meta_data_path.open(mode="rb") as meta_data, new_array_file_path.open(mode="rb") as array_data:
            data_upload = UploadedFile(meta_data_file=django.core.files.File(meta_data,
                                                                             name=new_meta_data_path.name),
                                       array_data_file=django.core.files.File(array_data,
                                                                                 name=new_array_file_path.name),
                                       center=center)
            with pytest.raises(ValidationError, match="Allowed extensions"):
                data_upload.full_clean()


@pytest.mark.django_db(databases=["default", "bsr"])
def test_get_center(centers, mock_data_from_files):
    center = Center.objects.get(name="jhu")
    assert get_center(center) is center

    from user.models import Center as UserCenter
    assert get_center(UserCenter.objects.get(pk=center.pk)) == center

    patient = Patient.objects.all()[0]
    patient.center = center
    patient.full_clean()
    patient.save()

    assert get_center(patient) is center

    for visit in patient.visit.all():
        assert get_center(visit) is center

    for bio_sample in visit.bio_sample.all():
        assert get_center(bio_sample) is center

    for array_data in bio_sample.array_data.all():
        assert get_center(array_data) is center

    for observation in Observation.objects.filter(visit__patient__center=center):
        assert get_center(observation) == center
        # assert get_center(observation.observable) is center  # TODO: Not yet related in observable.json fixture.
