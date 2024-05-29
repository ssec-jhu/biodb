from pathlib import Path

import pandas as pd
from django.conf import settings
from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models import Q

from biospecdb.util import get_object_or_raise_validation
import uploader.io


class ExitTransaction(Exception):
    ...


def save_data_to_db(meta_data, spectral_data, center=None, joined_data=None, dry_run=False) -> dict:

    """
    Ingest into the database large tables of observation & observable data (aka "meta" data) along with associated
    spectral data.

    Note: Data can be passed in pre-joined, i.e., save_data_to_db(None, None, joined_data). If so, data can't be
          validated.
    Note: This func is called by UploadedFile.clean() which, therefore, can't also be called here.
    """
    from uploader.models import BioSample, Observable, Instrument, Patient, SpectralData, Observation, UploadedFile,\
        Visit, Center as UploaderCenter
    from user.models import Center as UserCenter

    # Only user.models.User can relate to user.models,Center, all uploader models must use uploader.models.Center since
    # these two apps live on separate databases.
    if center and isinstance(center, UserCenter):
        center = UploaderCenter.objects.get(pk=center.pk)

    index_column = settings.BULK_UPLOAD_INDEX_COLUMN_NAME

    if joined_data is None:
        # Read in all data.
        meta_data = meta_data if isinstance(meta_data, pd.DataFrame) else \
            uploader.io.read_meta_data(meta_data, index_column=index_column)
        spec_data = spectral_data if isinstance(spectral_data, pd.DataFrame) else \
            uploader.io.read_spectral_data_table(spectral_data, index_column=index_column)

        UploadedFile.validate_lengths(meta_data, spec_data)
        joined_data = UploadedFile.join_with_validation(meta_data, spec_data)

    try:
        with transaction.atomic(using="bsr"):
            spectral_data_files = []

            # Ingest into db.
            for index, row in joined_data.iterrows():
                # NOTE: The pattern for column lookup is to use get(..., default=None) and defer the field validation,
                # i.e., whether null/blank etc., to the actual field def.

                # Patient
                try:
                    # NOTE: ValidationError is raised when ``index`` is not a UUID, or not UUID-like, e.g., 1 is ok (as
                    # it's an int), however, '1' isn't. Here ``index`` is a string - and needs to be for UUIDs.
                    opts = {index_column: index, "center": center}
                    patient = Patient.objects.get(**opts)
                except Patient.DoesNotExist:
                    # NOTE: The order of dicts matters here such that index_column clobbers that from
                    # Patient.parse_fields_from_pandas_series().
                    patient = Patient(**(Patient.parse_fields_from_pandas_series(row) | opts))
                    patient.full_clean()
                    patient.save()

                # Visit
                visit = Visit(patient=patient, **Visit.parse_fields_from_pandas_series(row))
                visit.full_clean()
                visit.save()

                # BioSample
                biosample = BioSample(visit=visit, **BioSample.parse_fields_from_pandas_series(row))
                biosample.full_clean()
                biosample.save()
                visit.bio_sample.add(biosample, bulk=False)

                # SpectralData
                instrument = get_object_or_raise_validation(Instrument, pk=row.get("instrument"))

                # Create datafile
                json_str = uploader.io.spectral_data_to_json(file=None,
                                                             data=None,
                                                             patient_id=patient.patient_id,
                                                             wavelength=row["wavelength"],
                                                             intensity=row["intensity"])

                spectraldata = SpectralData(instrument=instrument,
                                            bio_sample=biosample,
                                            **SpectralData.parse_fields_from_pandas_series(row))
                filename = f"{uploader.io.TEMP_FILENAME_PREFIX if dry_run else ''}{spectraldata.generate_filename()}"
                spectraldata.data = ContentFile(json_str, name=filename)
                spectraldata.full_clean()
                spectraldata.save()
                spectral_data_files.append(spectraldata.data)

                biosample.spectral_data.add(spectraldata, bulk=False)
                instrument.spectral_data.add(spectraldata, bulk=False)

                # Observations
                for observable in Observable.objects.filter(Q(center=center) | Q(center=None)):
                    observation_value = row.get(observable.alias.lower(), None)
                    if observation_value is None:
                        continue

                    # TODO: Should the following logic belong to Observation.__init__()?
                    #  See https://github.com/rispadd/biospecdb/issues/42
                    observation_value = Observable.Types(observable.value_class).cast(observation_value)
                    observation = Observation(observable=observable,
                                              visit=visit,
                                              observable_value=observation_value)
                    observation.full_clean()
                    observation.save()
                    observable.observation.add(observation, bulk=False)

            if dry_run:
                raise ExitTransaction()
    except ExitTransaction:
        pass
    except Exception:
        # Something went wrong and the above transaction was aborted so delete uncommitted and now orphaned files.
        while spectral_data_files:
            file = spectral_data_files.pop()
            if not file.closed:
                file.close()
            SpectralData.data.field.storage.delete(file.name)  # Pop to avoid repetition in finally branch.
        raise
    finally:
        # Delete unwanted temporary files.
        for file in spectral_data_files:
            if (filename := Path(file.name)).name.startswith(uploader.io.TEMP_FILENAME_PREFIX):
                if not file.closed:
                    file.close()
                SpectralData.data.field.storage.delete(filename)
