import pytest

from django.db.utils import OperationalError

from uploader.models import Disease, FullPatientView, SymptomsView, VisitSymptomsView, Symptom
from uploader.sql import execute_sql


@pytest.mark.django_db(databases=["default", "bsr"])
class TestViews:
    def test_symptoms_view(self, mock_data):
        all_view_data = SymptomsView.update_view(check=True, limit=None)
        all_symptoms = Symptom.objects.all()
        assert len(all_symptoms) > 1  # Check non-empty.
        assert len(all_view_data) == len(all_symptoms)

    def test_symptoms_view_django_model(self, mock_data):
        all_view_data = SymptomsView.update_view(limit=None)
        all_django_view_data = SymptomsView.objects.all()
        assert len(all_view_data) > 1  # Check non-empty.
        assert len(all_view_data) == len(all_django_view_data)

    def test_symptoms_view_django_model_filter(self, mock_data, sql_views):
        SymptomsView.update_view()
        week_long_symptoms_1 = execute_sql(f"""
                                           select *
                                           from {SymptomsView._meta.db_table}
                                           where days_symptomatic = 7
                                           """,
                                           db=SymptomsView.db)
        week_long_symptoms_2 = SymptomsView.objects.filter(days_symptomatic=7)
        assert len(week_long_symptoms_1) > 1  # Check non-empty.
        assert len(week_long_symptoms_1) == len(week_long_symptoms_2)

    def test_django_raise_on_missing_view(self, mock_data):
        SymptomsView.drop_view()
        with pytest.raises(OperationalError, match="no such table:"):
            # NOTE: Django ORM queries are lazy, so we call exists() instead of all() as the latter is lazy.
            SymptomsView.objects.exists()

    def test_visit_symptoms_view(self, mock_data):
        VisitSymptomsView.update_view(check=True)

    def test_full_patient_view(self, mock_data):
        FullPatientView.update_view(check=True)

    def test_view_dependencies(self, mock_data):
        SymptomsView.drop_view()
        with pytest.raises(OperationalError, match="no such table:"):
            SymptomsView.objects.exists()

        VisitSymptomsView.drop_view()
        with pytest.raises(OperationalError, match="no such table:"):
            VisitSymptomsView.objects.exists()

        # This view should create its view dependencies which are the two above.
        FullPatientView.update_view()

        SymptomsView.objects.exists()
        VisitSymptomsView.objects.exists()
        FullPatientView.objects.exists()

    def test_view_caching(self, mock_data):
        """
            FullPatientView depends on VisitSymptomsView, if VisitSymptomsView is updated does FullPatientView see the
            updated view or does it point to some older cached/inlined view?
            With sqlite, it sees the newer updated view, but we should test to help us detect otherwise if we change the
            DB backend.
        """

        FullPatientView.update_view()

        # Sanity check that the new disease does not exist.
        with pytest.raises(OperationalError, match="no such column:"):
            execute_sql(f"select my_new_disease from {FullPatientView._meta.db_table}", db=FullPatientView.db)

        # Add new disease.
        disease = Disease(name="my_new_disease")
        disease.clean()
        disease.save(update_view=False)

        # Sanity check it still doesn't exist without ANY view update.
        with pytest.raises(OperationalError, match="no such column:"):
            execute_sql(f"select my_new_disease from {FullPatientView._meta.db_table}", db=FullPatientView.db)

        # Update view dependency
        FullPatientView.sql_view_dependencies[0].update_view()

        # Assert that new disease exists without having updated actual view.
        execute_sql(f"select my_new_disease from {FullPatientView._meta.db_table}", db=FullPatientView.db)

    def test_view_update_on_disease_save(self, mock_data):
        FullPatientView.update_view()

        # Sanity check that the new disease does not exist.
        with pytest.raises(OperationalError, match="no such column:"):
            execute_sql(f"select my_new_disease from {FullPatientView._meta.db_table}", db=FullPatientView.db)

        # Add new disease.
        Disease.objects.create(name="my_new_disease")

        # Assert that new disease exists without having updated actual view.
        execute_sql(f"select my_new_disease from {FullPatientView._meta.db_table}", db=FullPatientView.db)

    def test_update_sql_views_command(self, mock_data, sql_views):
        resp = execute_sql(f"select * from {FullPatientView._meta.db_table}", db=FullPatientView.db)
        assert len(resp) == 10