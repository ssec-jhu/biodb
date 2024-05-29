import dataclasses
from io import IOBase
import json
from pathlib import Path
from uuid import UUID

from django.conf import settings
import django.core.files
from django.core.files.base import ContentFile
from django.core.files.storage import storages
import django.core.files.uploadedfile
from django.core.serializers.json import DjangoJSONEncoder
import pandas as pd
from pandas._libs.parsers import STR_NA_VALUES

from biodb.util import StrEnum, to_uuid

# TODO: move to settings
DEFAULT_PATIENT_ID_STR = "patient_id"
PATIENT_UUID_STR_ALLOWED_ALIASES = {"patient_id": ["patient id", "Patient ID", "PATIENT ID"],
                                    "patient_cid": ["patient cid", "Patient CID", "PATIENT CID"]}


@dataclasses.dataclass
class SpectralData:
    patient_id: UUID
    wavelength: list
    intensity: list

    def __post_init__(self):
        self.patient_id = to_uuid(self.patient_id)

    def to_json(self, filename, **kwargs):
        return spectral_data_to_json(filename, data=self, **kwargs)


JSON_OPTS = {"indent": None, "force_ascii": True}  # jsonlines.
TEMP_FILENAME_PREFIX = "__TEMP__"


class DataSchemaError(Exception):
    ...


class FileFormats(StrEnum):
    CSV = ".csv"
    XLSX = ".xlsx"
    JSONL = ".jsonl"

    @classmethod
    def choices(cls):
        return [x.value.replace('.', '') for x in cls]  # Remove '.' for django validator.


def _clean_df(df, inplace=False):
    # Note: Some (if not all) pandas funcs return None when `inplace=True` instead of a ref to the passed df, making for
    # awkward assignment due to the conditional return.

    cleaned_df = df

    _cleaned_df = cleaned_df.rename(columns=lambda x: x.lower() if isinstance(x, str) else x, inplace=inplace)
    cleaned_df = cleaned_df if inplace else _cleaned_df

    _cleaned_df = cleaned_df.rename(columns={x: k for k, v in PATIENT_UUID_STR_ALLOWED_ALIASES.items() for x in v},
                                    inplace=inplace,
                                    errors="ignore")
    cleaned_df = cleaned_df if inplace else _cleaned_df

    # Note: This func is used to read in the data table returned from an SQL query from the explorer app and therefore,
    # may not contain a PATIENT_ID_STR column - ``dropna`` has no ``errors`` arg.
    index_columns = set(PATIENT_UUID_STR_ALLOWED_ALIASES) & set(cleaned_df.columns)
    if index_columns:
        # TODO: Raise on null patient id instead of silently dropping possible data.
        _cleaned_df = cleaned_df.dropna(subset=list(index_columns), inplace=inplace)
        cleaned_df = cleaned_df if inplace else _cleaned_df

    return cleaned_df


def _read_raw_data(file, ext=None):
    """ Read data from file-like or path-like object. """
    fp, filename = _get_file_info(file)

    # We need an ext to determine which reader to use. If one isn't explicitly passed, obtain from filename.
    if not ext:
        if filename:
            ext = filename.suffix.lower()
        else:
            raise ValueError(f"When passing an IO stream, ext must be specified as one of '{FileFormats.list()}'.")

    # Choose which to actually read from.
    if fp:
        file = fp
    elif filename:
        file = filename
    else:
        raise ValueError("A path-like or file-like object must be specified.")

    # NOTE: Reading the patient ID & CID as a str is crucial for converting to UUIDs as floats cannot be safely
    # converted nor is it ok to read in as int as they could be actual UUID str.
    type_mapping = {y: str for x in PATIENT_UUID_STR_ALLOWED_ALIASES.values() for y in x} | \
                   {x: str for x in PATIENT_UUID_STR_ALLOWED_ALIASES}
    kwargs = dict(true_values=["yes", "Yes"],  # In addition to case-insensitive variants of True.
                  false_values=["no", "No"],  # In addition to case-insensitive variants of False.
                  na_values=[' ', "unknown", "Unknown", "na", "none"],
                  dtype=type_mapping)
    # NOTE: The following default na_values are also used:
    # ‘’, ‘  # N/A’, ‘#N/A N/A’, ‘#NA’, ‘-1.#IND’, ‘-1.#QNAN’, ‘-NaN’, ‘-nan’, ‘1.#IND’, ‘1.#QNAN’, ‘<NA>’, ‘N/A’, ‘NA’,
    # ‘NULL’, ‘NaN’, ‘None’, ‘n/a’, ‘nan’, ‘null’.

    # NOTE: When the file size is > 2.5M Django will chunk and this will need to be handled. See
    # https://github.com/rispadd/biodb/issues/38
    if ext == FileFormats.CSV:
        data = pd.read_csv(file, **kwargs)
    elif ext == FileFormats.XLSX:
        data = pd.read_excel(file, **kwargs)
    elif ext == FileFormats.JSONL:
        data = pd.read_json(file, orient="records", lines=True, dtype=kwargs["dtype"])
        data.replace(kwargs["true_values"], True, inplace=True)
        data.replace(kwargs["false_values"], False, inplace=True)
        data.replace(STR_NA_VALUES.union(kwargs['na_values']), pd.NA, inplace=True)
    else:
        raise NotImplementedError(f"File ext must be one of {FileFormats.list()} not '{ext}'.")

    # Clean.
    data = _clean_df(data, inplace=True)

    return data


def read_meta_data(file, index_column=settings.BULK_UPLOAD_INDEX_COLUMN_NAME):
    """ Read in bulk upload meta data file of all Observations and parsable model fields. """
    df = _read_raw_data(file)

    # Set index.
    cleaned_data = df.set_index(index_column)

    # Insist on index as UUIDs.
    cleaned_data = cleaned_data.set_index(cleaned_data.index.map(lambda x: to_uuid(x)))

    # Replace na & '' with None via na -> '' -> None
    cleaned_data = cleaned_data.fillna('').replace('', None)

    return cleaned_data


def read_spectral_data_table(file, index_column=DEFAULT_PATIENT_ID_STR):
    """ Read in multiple rows of data returning a pandas.DataFrame.

        The data to be read in, needs to be of the following table layout for .csv & .xlsx:
        Note: Commas need to be present for CSV data.
        Note: The following docstring uses markdown table syntax.
        | patient_id | min_lambda | ... | max_lambda |
        | ---------- | ---------- | --- | ---------- |
        |<some UUID> | intensity  | ... | intensity  |

        For .jsonl each line/row must be of the following:
        {"patient_id": value, wavelength_value: intensity_value, wavelength_value: intensity_value, ...}

        For json data of the following form use ``read_spectral_data()``.
        {"patient_id": value, "wavelength": [values], "intensity": [values]}
    """
    df = _read_raw_data(file)

    # Clean.
    spec_only = df.drop(columns=[index_column], inplace=False, errors="raise")
    wavelengths = spec_only.columns.tolist()
    specv = spec_only.values.tolist()
    freqs = [wavelengths for i in range(len(specv))]

    df = pd.DataFrame({index_column: [to_uuid(x) for x in df[index_column]],
                       "wavelength": freqs,
                       "intensity": specv})

    df.set_index(index_column, inplace=True, drop=False)
    return df


def read_single_row_spectral_data_table(file, index_column=DEFAULT_PATIENT_ID_STR):
    """ Read in single row spectral data.

        The data to be read in, needs to be of the following table layout for .csv & .xlsx:
        Note: Commas need to be present for CSV data.
        Note: The following docstring uses markdown table syntax.
        Note: This is as for ``read_spectral_data_table`` except that it contains data for only a single
        patient, i.e., just a single row:
        | patient_id | min_lambda | ... | max_lambda |
        | ---------- | ---------- | --- | ---------- |
        |<some UUID> | intensity  | ... | intensity  |

        For .jsonl each line/row must be:
        {"patient_id": value, wavelength_value: intensity_values, wavelength_value: intensity_values, ...}

        For json data of the following form use ``read_spectral_data()``.
        {"patient_id": value, "wavelength": [values], "intensity": [values]}
    """

    df = read_spectral_data_table(file, index_column=index_column)

    if (length := len(df)) != 1:
        raise ValueError(f"The file read should contain only a single row not '{length}'")

    data = df.iloc[0]
    return SpectralData(data.patient_id, data.wavelength, data.intensity)


def spectral_data_to_json(file, data: SpectralData, patient_id=None, wavelength=None, intensity=None, **kwargs):
    """ Convert data to json equivalent to {"patient_id": value, "wavelength": [values], "intensity": [values]}
        Returns json str and/or writes to file.
    """

    if not data:
        assert patient_id is not None
        assert wavelength is not None
        assert intensity is not None
        data = dict(patient_id=patient_id, wavelength=wavelength, intensity=intensity)

    if isinstance(data, SpectralData):
        data = dataclasses.asdict(data)

    opts = dict(indent=JSON_OPTS["indent"], ensure_ascii=JSON_OPTS["force_ascii"], cls=DjangoJSONEncoder)
    opts.update(kwargs)

    if file is None:
        return json.dumps(data, **opts)
    elif isinstance(file, (str, Path)):
        return storages["default"].save(file, ContentFile(json.dumps(data, **opts), name=file))
    else:
        # Note: We assume that this is pointing to the correct section of the file, i.e., the beginning.
        json.dump(data, file, **opts)


def spectral_data_from_json(file):
    """ Read spectral data of the form {"patient_id": value, "wavelength": [values], "intensity": [values]}
        and return data SpectralData instance.
    """
    # Determine whether file obj (fp) or filename.
    fp, filename = _get_file_info(file)
    ext = filename.suffix

    if ext != FileFormats.JSONL:
        raise ValueError(f"Incorrect file format - expected '{FileFormats.JSONL}' but got '{ext}'")

    if fp:
        # Note: We assume that this is pointing to the correct section of the file, i.e., the beginning.
        data = json.load(fp)
    elif filename:
        with storages["default"].open(filename, mode="r") as fp:
            data = json.load(fp)
    else:
        raise ValueError("A path-like or file-like object must be specified.")

    # Check that the json is as expected. This is needed for validation when a user provides json data.
    if (fields := {x.name for x in dataclasses.fields(SpectralData)}) != data.keys():
        raise DataSchemaError(f"Schema error: expected only the fields '{fields}' but got '{data.keys()}'")

    return SpectralData(**data)


def read_spectral_data(file):
    """ General purpose reader to handle multiple file formats returning SpectralData instance.

        The data to be read in, needs to be of the following table layout for .csv & .xlsx:
        Note: Commas need to be present for CSV data.
        Note: The following docstring uses markdown table syntax.
        Note: This is as for ``read_spectral_data_table`` except that it contains data for only a single
        patient, i.e., just a single row:
        | patient_id | min_lambda | ... | max_lambda |
        | ---------- | ---------- | --- | ---------- |
        |<some UUID> | intensity  | ... | intensity  |

        For .jsonl data must be of the following form:
        {"patient_id": value, "wavelength": [values], "intensity": [values]}
    """
    _fp, filename = _get_file_info(file)
    ext = filename.suffix

    data = spectral_data_from_json(file) if ext == FileFormats.JSONL else read_single_row_spectral_data_table(file)
    return data


def _get_file_info(file):
    """ The actual file buffer is nested at different levels depending on container class.

        Returns: (fp, Path(filename))
    """
    # Handle base types.
    if file is None:
        return None, None
    elif isinstance(file, str):
        return None, Path(file)
    elif isinstance(file, Path):
        return None, file
    elif isinstance(file, IOBase):
        return file, None

    # Handle Django types.
    if isinstance(file, django.core.files.uploadedfile.TemporaryUploadedFile):
        fp = file.file.file
    elif isinstance(file, django.core.files.File):
        fp = file.file
    else:
        raise NotImplementedError(type(file))

    # The file may have already been read but is still open - so rewind. TODO: potential conflict with #38?
    if hasattr(fp, "closed") and not file.closed and hasattr(fp, "seek"):
        fp.seek(0)
    return fp, Path(file.name)
