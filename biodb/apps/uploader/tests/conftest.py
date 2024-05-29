from pathlib import Path
import shutil
from uuid import uuid4

from django.conf import settings
import django.core.files
from django.core.management import call_command
from django.test import RequestFactory
from explorer.models import Query
from explorer.tests.factories import UserFactory as ExplorerUserFactory
from factory import Sequence, SubFactory
from factory.django import DjangoModelFactory
import pytest


from biospecdb.util import find_package_location
from uploader.models import SpectralData, UploadedFile, Center
from user.models import Center as UserCenter

DATA_PATH = Path(__file__).parent / "data"


@pytest.fixture(scope="function", autouse=True)
def exec_custom_markers(request, monkeypatch):
    auto_find = request.node.get_closest_marker("auto_find_previous_visit")
    if auto_find:
        monkeypatch.setattr(settings, "AUTO_FIND_PREVIOUS_VISIT", auto_find.args[0])

    # TODO: add all the other existing ones in here.


class CenterFactory(DjangoModelFactory):

    class Meta:
        model = UserCenter

    id = uuid4()
    name = Sequence(lambda n: 'name %03d' % n)
    country = Sequence(lambda n: 'country %03d' % n)


class UserFactory(ExplorerUserFactory):
    center = SubFactory(CenterFactory)


def rm_dir(path):
    if path.exists() and path.is_dir():
        shutil.rmtree(path)
        assert not path.exists()


def rm_all_media_dirs():
    from catalog.models import Dataset
    # Tidy up any created files.
    rm_dir(Path(UploadedFile.UPLOAD_DIR))
    rm_dir(Path(SpectralData.UPLOAD_DIR))
    rm_dir(Path(Dataset.UPLOAD_DIR))


@pytest.fixture(scope="function", autouse=True)
def clean_up():
    yield
    rm_all_media_dirs()


class SimpleQueryFactory(DjangoModelFactory):

    class Meta:
        model = Query

    title = Sequence(lambda n: f'My simple query {n}')
    sql = "select * from spectral_data"
    description = "Stuff"
    connection = settings.EXPLORER_DEFAULT_CONNECTION
    created_by_user = SubFactory(UserFactory)


@pytest.fixture(scope="function")
def django_request(center):
    request = RequestFactory()
    user = UserFactory()
    user.center = UserCenter.objects.get(name="spadda")
    request.user = user
    return request


@pytest.fixture(scope="function")
def centers(django_db_blocker):
    with django_db_blocker.unblock():
        call_command('loaddata', "centers")
        call_command("loaddata",  "--database=bsr", "centers")


@pytest.fixture(scope="function")
def center(centers):
    return Center.objects.get(name="spadda")


@pytest.fixture(scope="function")
def sql_views(django_db_blocker):
    with django_db_blocker.unblock():
        call_command("update_sql_views", "flat_view")


@pytest.fixture(scope="function")
def bio_sample_types(django_db_blocker):
    with django_db_blocker.unblock():
        call_command('loaddata', "--database=bsr", 'biosampletypes.json')


@pytest.fixture(scope="function")
def spectra_measurement_types(django_db_blocker):
    with django_db_blocker.unblock():
        call_command('loaddata', "--database=bsr", 'spectrameasurementtypes.json')


@pytest.fixture(scope="function")
def observables(django_db_blocker):
    with django_db_blocker.unblock():
        call_command('loaddata', "--database=bsr", 'observables.json')


@pytest.fixture(scope="function")
def instruments(django_db_blocker):
    with django_db_blocker.unblock():
        call_command('loaddata', "--database=bsr", 'instruments.json')


@pytest.fixture(scope="function")
def patients(django_db_blocker, centers):
    with django_db_blocker.unblock():
        call_command('loaddata', "--database=bsr",
                     str(find_package_location() / 'apps/uploader/tests/data/patients.json'))


@pytest.fixture(scope="function")
def visits(patients, django_db_blocker):
    with django_db_blocker.unblock():
        call_command('loaddata', "--database=bsr",
                     str(find_package_location() / 'apps/uploader/tests/data/visits.json'))


@pytest.fixture(scope="function")
def qcannotators(db, django_db_blocker):
    with django_db_blocker.unblock():
        call_command('loaddata', "--database=bsr", 'qcannotators.json')


@pytest.fixture(scope="function")
def mock_data(db, django_db_blocker, centers):
    # NOTE: Since this loads directly to the DB without any validation and thus call to loaddata(), no data files are
    # present. If you need actual spectral data, use ``mock_data_from_files`` below instead.
    with django_db_blocker.unblock():
        call_command('loaddata', "--database=bsr", 'test_data.json')


def bulk_upload():
    meta_data_path = (DATA_PATH / "meta_data").with_suffix(UploadedFile.FileFormats.XLSX)
    spectral_file_path = (DATA_PATH / "spectral_data").with_suffix(UploadedFile.FileFormats.XLSX)
    with meta_data_path.open(mode="rb") as meta_data:
        with spectral_file_path.open(mode="rb") as spectral_data:
            data_upload = UploadedFile(meta_data_file=django.core.files.File(meta_data,
                                                                             name=meta_data_path.name),
                                       spectral_data_file=django.core.files.File(spectral_data,
                                                                                 name=spectral_file_path.name),
                                       center=Center.objects.get(name="spadda"))
            data_upload.clean()
            data_upload.save()


@pytest.fixture(scope="function")
def mock_data_from_files(request,
                         monkeypatch,
                         db,
                         centers,
                         observables,
                         django_db_blocker,
                         instruments,
                         bio_sample_types,
                         spectra_measurement_types):
    # patch MEDIA_ROOT
    media_root = request.node.get_closest_marker("media_root")
    if media_root:
        monkeypatch.setattr(settings, "MEDIA_ROOT", media_root.args[0])

    # Turn off auto annotation functionality so that it isn't always being tested.
    auto_annotate = False if getattr(request, "param", None) is None else request.param
    monkeypatch.setattr(settings, "AUTO_ANNOTATE", auto_annotate)

    with django_db_blocker.unblock():
        bulk_upload()

    yield

    # Tidy up any created files.
    rm_all_media_dirs()
