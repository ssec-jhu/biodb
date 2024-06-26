import dataclasses
import zipfile
from pathlib import Path

import pytest
import uploader.io
from django.conf import settings
from uploader.exporters import CSVExporter
from uploader.models import ArrayData
from uploader.tests.conftest import SimpleQueryFactory


@pytest.fixture()
def csv_export(request, monkeypatch, mock_data_from_files):
    # patch EXPLORER_DATA_EXPORTERS_INCLUDE_DATA_FILES
    include_data_files = request.node.get_closest_marker("include_data_files")
    if include_data_files:
        monkeypatch.setattr(settings, "EXPLORER_DATA_EXPORTERS_INCLUDE_DATA_FILES", include_data_files.args[0])

    # patch EXPLORER_DATA_EXPORTERS_ALLOW_DATA_FILE_ALIAS
    allow_aliases = request.node.get_closest_marker("allow_aliases")
    if allow_aliases:
        monkeypatch.setattr(settings, "EXPLORER_DATA_EXPORTERS_ALLOW_DATA_FILE_ALIAS", allow_aliases.args[0])

    sql_marker = request.node.get_closest_marker("sql")
    sql = sql_marker.args[0] if sql_marker and sql_marker.args[0] else "select * from array_data"

    q = SimpleQueryFactory(sql=sql)
    exporter = CSVExporter(query=q)
    output = exporter.get_output()
    return output


@pytest.mark.django_db(databases=["default", "bsr"])
@pytest.mark.parametrize(
    tuple(),
    [
        pytest.param(marks=pytest.mark.allow_aliases(False)),
        pytest.param(marks=pytest.mark.allow_aliases(True)),
        pytest.param(marks=pytest.mark.media_root("")),
        pytest.param(marks=pytest.mark.media_root("my_media/")),
    ],
)
class TestExporters:
    @pytest.mark.include_data_files(False)
    def test_without_data_files(self, csv_export):
        assert isinstance(csv_export, str)
        assert len(csv_export.splitlines()) == 10 + 1  # +1 for column header.

    @pytest.mark.include_data_files(True)
    @pytest.mark.parametrize(
        tuple(),
        [
            pytest.param(marks=pytest.mark.sql("select data, data from array_data")),
            pytest.param(marks=pytest.mark.sql(None)),
        ],
    )
    def test_no_duplicate_data_files(self, csv_export):
        assert zipfile.is_zipfile(csv_export)
        z = zipfile.ZipFile(csv_export)
        assert len(z.namelist()) == 10 + 1  # +1 for .csv data file.

    @pytest.mark.include_data_files(True)
    def test_with_data_files_check_content(self, csv_export):
        z = zipfile.ZipFile(csv_export)
        namelist = z.namelist()
        array_data_dir = Path(ArrayData.data.field.upload_to)

        array_data_files = []
        query_data_file = []
        for filename in namelist:
            if Path(filename).parent == array_data_dir:
                array_data_files.append(filename)
            else:
                query_data_file.append(filename)

        assert len(array_data_files) == 10
        assert len(query_data_file) == 1

        query_data_file = query_data_file[0]
        with z.open(query_data_file) as f:
            data = uploader.io._read_raw_data(f, ext=Path(query_data_file).suffix)
            assert len(data) == 10
            assert set(data[ArrayData.data.field.name]) == set(array_data_files)

        for filename in array_data_files:
            data = uploader.io.read_array_data(filename)
            assert isinstance(data, uploader.io.ArrayData)

            assert {x.name for x in dataclasses.fields(data)} == {"patient_id", "x", "y"}
            assert data.patient_id == ArrayData.objects.get(data=filename).bio_sample.visit.patient.patient_id
            assert len(data.x) == 1798
            assert len(data.y) == 1798

    @pytest.mark.include_data_files(True)
    @pytest.mark.sql("select * from patient")  # uploader_patient contains no array data.
    def test_no_data(self, csv_export):
        assert isinstance(csv_export, str)
