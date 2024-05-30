from inspect import signature

from django.apps import apps
from django.conf import settings
from django.core.exceptions import NON_FIELD_ERRORS, ObjectDoesNotExist, ValidationError
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.db.models import Manager, Q
from django.db.utils import OperationalError, ProgrammingError
from django import forms
from nested_admin import NestedStackedInline, NestedTabularInline, NestedModelAdmin

from biodb.util import to_bool
from .models import BioSample, Observable, Instrument, Patient, ArrayData, Observation, UploadedFile, Visit,\
    QCAnnotator, QCAnnotation, Center, get_center, BioSampleType, ArrayMeasurementType
from uploader.forms import ModelForm
from user.admin import CenterAdmin as UserCenterAdmin

User = get_user_model()


class ModelAdmin(admin.ModelAdmin):
    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj=obj, **kwargs)
        setattr(form, "_post_clean", ModelForm._post_clean)
        return form


class RestrictedByCenterMixin:
    """ Restrict admin access to objects belong to user's center. """
    def _has_perm(self, request, obj):
        if (request.user is None) or (obj is None):
            return False # Strict security.

        try:
            if not (user_center := request.user.center):
                return False  # Strict security.
        except User.center.RelatedObjectDoesNotExist:
            return False  # Strict security.

        obj_center = get_center(obj)

        if isinstance(obj_center, Manager):
            if obj_center.count():
                return user_center in obj_center.all()
            else:
                # Objects without centers are "owned" by all.
                return True

        if not obj_center:
            # This func is called for new obj forms where obj.center obviously hasn't been set yet. In this scenario
            # limited visibility is deferred to self.formfield_for_foreignkey.
            return True

        return obj_center == user_center

    def has_view_permission(self, request, obj=None):
        has_base_perm = super().has_view_permission(request, obj=obj)

        if obj is None or request.user.is_superuser:
            return has_base_perm

        return has_base_perm and self._has_perm(request, obj)

    def has_module_permission(self, request):
        return super().has_module_permission(request)

    def has_add_permission(self, request, obj=None):
        # Note: The signature isn't symmetric for ``admin.ModelAdmin`` and ``admin.InlineModelAdmin`` so we introspect
        # their func signatures. Their signatures are:
        # * ``admin.ModelAdmin.has_add_permission(self, request)``
        # * ``admin.InlineModelAdmin.has_add_permission(self, request, obj=None)``
        kwargs = {"obj": obj} if "obj" in signature(super().has_add_permission).parameters else {}
        return super().has_add_permission(request, **kwargs)

    def has_change_permission(self, request, obj=None):
        has_base_perm = super().has_change_permission(request, obj=obj)

        if obj is None or request.user.is_superuser:
            return has_base_perm

        return has_base_perm and self._has_perm(request, obj)

    def has_delete_permission(self, request, obj=None):
        has_base_perm = super().has_delete_permission(request, obj)

        if obj is None or request.user.is_superuser:
            return has_base_perm

        return has_base_perm and self._has_perm(request, obj)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        """ Limit center form fields to user's center, and set initial value as such.
            Exceptions are made for superusers.
        """
        field = super().formfield_for_foreignkey(db_field, request, **kwargs)

        if request.user.is_superuser:
            return field

        # User.center can't be Null so this isn't actually possible, but just in case return an empty queryset.
        try:
            if not request.user.center:
                field.queryset = field.queryset.none()
                return field
        except User.center.RelatedObjectDoesNotExist:
            field.queryset = field.queryset.none()
            return field

        center = Center.objects.get(pk=request.user.center.pk)

        if db_field.name == "center":
            field.initial = center
            field.queryset = field.queryset.filter(pk=request.user.center.pk)
        elif db_field.name in ("observable", "instrument"):
            # For these fields a Null center implies visible to all centers.
            field.queryset = field.queryset.filter(Q(center=center) | Q(center=None))
        elif db_field.name == "patient":
            field.queryset = field.queryset.filter(center=center)
        elif db_field.name == "visit":
            field.queryset = field.queryset.filter(patient__center=center)
        elif db_field.name == "previous_visit":
            field.queryset = field.queryset.filter(patient__center=center)
        elif db_field.name == "next_visit":
            field.queryset = field.queryset.filter(patient__center=center)
        elif db_field.name == "observation":
            field.queryset = field.queryset.filter(visit__center=center)
        elif db_field.name == "bio_sample":
            field.queryset = field.queryset.filter(visit__patient__center=center)
        elif db_field.name == "array_data":
            field.queryset = field.queryset.filter(bio_sample__visit__patient__center=center)
        elif db_field.name == "qc_annotation":
            field.queryset = field.queryset.filter(array_data__bio_sample__visit__patient__center=center)
        elif db_field.name in ("annotator", "measurement_type", "sample_type"):
            # These aren't limited/restricted by center.
            pass
        else:
            # For extra security raise rather than return leaky data.
            raise NotImplementedError(f"Whoops! Looks like someone forgot to account for '{db_field.name}'!")

        return field


admin.site.register(BioSampleType)
admin.site.register(ArrayMeasurementType)


@admin.register(Instrument)
class InstrumentAdmin(RestrictedByCenterMixin, ModelAdmin):
    readonly_fields = ["created_at", "updated_at"]  # TODO: Might need specific user group.
    list_display = ["id", "manufacturer", "model"]
    list_filter = ("manufacturer", "model")
    ordering = ["manufacturer"]

    fieldsets = [
        (
            None,
            {
                "fields": [("id", "cid"),
                           "manufacturer",
                           "model",
                           "serial_number",
                           "center"]
            }
        ),
        (
            "More Details",
            {
                "classes": ["collapse"],
                "fields": [("created_at", "updated_at")],
            }
        ),
    ]


class UploadedFileForm(ModelForm):
    def add_error(self, field, error):
        """ Override this method for validation errors that aren't fields of this form.

            Django Validation errors contain dicts where the keys are field names and their values a list of exceptions.
            This is so exceptions are render beside their corresponding field widget in the form.
            In the case of bulk uploads, validation errors can occur for fields NOT belonging to the form, e.g.,
            patient_id, visit, etc, - basically everything. When this happens Django will raise an exception which is
            undesirable. Instead, we map the field to ``NON_FIELD_ERRORS`` which Django then correctly renders in the form.
        """

        try:
            return super().add_error(field, error)
        except ValueError:
            if field or (not isinstance(error, ValidationError)) or (not hasattr(error, "error_dict")):
                raise

            for key in error.error_dict.copy():
                if key not in self.fields:
                    if NON_FIELD_ERRORS in error.error_dict:
                        # Note: Values for error_dict are always lists, so we can blindly append.
                        error.error_dict[NON_FIELD_ERRORS].append(error.error_dict.pop(key))
                    else:
                        error.error_dict[NON_FIELD_ERRORS] = error.error_dict.pop(key)
            # Try again.
            return super().add_error(None, error)


@admin.register(UploadedFile)
class UploadedFileAdmin(RestrictedByCenterMixin, ModelAdmin):
    form = UploadedFileForm
    search_fields = ["created_at"]
    search_help_text = "Creation timestamp"
    list_display = ["pk", "created_at", "meta_data_file", "array_data_file", "center"]
    readonly_fields = ["created_at", "updated_at"]  # TODO: Might need specific user group.
    date_hierarchy = "created_at"
    ordering = ("-updated_at",)
    list_filter = ("center",)

    def get_queryset(self, request):
        """ List only objects belonging to user's center. """
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        return qs.filter(center=Center.objects.get(pk=request.user.center.pk))


class QCAnnotationInline(RestrictedByCenterMixin, NestedTabularInline):
    model = QCAnnotation
    extra = 1
    min_num = 0
    show_change_link = True

    def get_extra(self, request, obj=None, **kwargs):
        # Only display inlines for those that exist, i.e., no expanded extras (if they exist).
        return 0 if obj and obj.pk and obj.qc_annotation.count() else self.extra


@admin.register(QCAnnotation)
class QCAnnotationAdmin(RestrictedByCenterMixin, ModelAdmin):
    search_fields = ["annotator__name",
                     "array_data__bio_sample__visit__patient__patient_id",
                     "array_data__bio_sample__visit__patient__patient_cid"]
    search_help_text = "Annotator Name, Patient ID or CID"
    readonly_fields = ("value", "created_at", "updated_at")  # TODO: Might need specific user group for timestamps.
    list_display = ["annotator_name", "value", "annotator_value_type", "updated_at"]
    ordering = ("-updated_at",)
    list_filter = ("array_data__bio_sample__visit__patient__center", "annotator__name")

    @admin.display
    def annotator_name(self, obj):
        return obj.annotator.name

    @admin.display
    def annotator_value_type(self, obj):
        return obj.annotator.value_type

    def get_queryset(self, request):
        """ List only objects belonging to user's center. """
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        center = Center.objects.get(pk=request.user.center.pk)
        return qs.filter(array_data__bio_sample__visit__patient__center=center)


@admin.register(QCAnnotator)
class QCAnnotatorAdmin(RestrictedByCenterMixin, ModelAdmin):
    search_fields = ["name"]
    search_help_text = "Name"
    # TODO: Might need specific user group for timestamps.)
    readonly_fields = ("created_at", "updated_at")
    ordering = ("name",)
    list_display = ["name", "fully_qualified_class_name", "default", "value_type"]


@admin.register(Observable)
class ObservableAdmin(RestrictedByCenterMixin, NestedModelAdmin):
    readonly_fields = ["created_at", "updated_at"]  # TODO: Might need specific user group.
    ordering = ["name"]
    search_fields = ["name"]
    search_help_text = "Observable name"
    list_filter = ("center", "category", "value_class")
    list_display = ["name", "description", "category", "observation_count"]

    @admin.display
    def observation_count(self, obj):
        return obj.observation.count()

    def get_queryset(self, request):
        """ List only objects belonging to user's center. """
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        return qs.filter(Q(center=Center.objects.get(pk=request.user.center.pk)) | Q(center=None))


class ObservationMixin:
    readonly_fields = ["created_at", "updated_at"]  # TODO: Might need specific user group.
    ordering = ("-updated_at",)

    fieldsets = [
        (
            None,
            {
                "fields": ["visit",
                           "observable",
                           "observable_value"]
            }
        ),
        (
            "More details",
            {
                "classes": ["collapse"],
                "fields": ["days_observed",
                           ("created_at", "updated_at")]
            }
        )
    ]

    @admin.display
    def patient_id(self, obj):
        return obj.visit.patient.patient_id

    @admin.display
    def observable_name(self, obj):
        return obj.observable.name

    def get_queryset(self, request):
        """ List only objects belonging to user's center. """
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        return qs.filter(visit__patient__center=Center.objects.get(pk=request.user.center.pk))


class ObservationInlineForm(ModelForm):
    observables = iter([])

    @staticmethod
    def _get_widget(value_class, choices=()):
        value_class = Observable.Types(value_class)
        if value_class is Observable.Types.BOOL:
            widget = forms.CheckboxInput(check_test=to_bool)
        elif value_class is Observable.Types.FLOAT:
            widget = forms.NumberInput()
        elif value_class is Observable.Types.INT:
            widget = forms.NumberInput()
        elif value_class is Observable.Types.STR:
            if choices:
                widget = forms.Select(choices=Observable.djangofy_choices(choices))
            else:
                widget = forms.TextInput()
        else:
            raise NotImplementedError(f"Dev error: missing widget mapping for type '{value_class}'.")
        return widget

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        observable = None
        if instance := kwargs.get("instance"):
            observable = instance.observable
        else:
            try:
                observable = next(self.observables)
                self.fields["observable"].initial = observable
            except StopIteration:
                pass

        if observable:
            self.fields["observable"].queryset = Observable.objects.filter(name=observable.name)
            self.fields["observable_value"].widget = self._get_widget(observable.value_class,
                                                                      choices=observable.value_choices)


class ObservationInline(ObservationMixin, RestrictedByCenterMixin, NestedTabularInline):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        try:
            # Only auto-populate "global" observables, i.e., those not related to a specific center (center=null).
            query = Q(center=None)
            if hasattr(self, "verbose_name"):  # Only Inline admins have verbose names.
                query &= Q(category=self.verbose_name.upper())
            kwargs = {"observables": iter(Observable.objects.filter(query))}
        except (OperationalError, ProgrammingError):
            kwargs = {}
        self.form = type("NewObservationForm", (ObservationInlineForm,), kwargs)

    extra = 0
    model = Observation
    show_change_link = True
    fk_name = "visit"

    # Override fieldsets from ObservationMixin as fields & fieldsets cannot both be set.
    fieldsets = None
    fields = ["observable", "observable_value"]

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        """ Limit observable to user's center (super's functionality) and admin category. """
        field = super().formfield_for_foreignkey(db_field, request, **kwargs)
        if db_field.name == "observable":
            field.queryset = field.queryset.filter(category=self.verbose_name.upper())
        return field

    def get_queryset(self, request):
        """ Limit observable to user's center and admin category. """
        qs = super().get_queryset(request)
        center = Center.objects.get(pk=request.user.center.pk)
        query = Q(observable__category=self.verbose_name.upper()) & \
            (Q(visit__patient__center=center) | Q(visit__patient__center=None))
        return qs.filter(query)

    def get_extra(self, request, obj=None, **kwargs):
        """ Only list extra inline forms when no data exists, i.e., new patient form. """
        if obj and obj.pk and obj.observation.count():
            # Only display inlines for those that exist, i.e., no extras (when self.extra=0).
            return self.extra

        # For whatever reason, obj=None when it shouldn't be, so we grab the ID from the resolver.
        obj, model = get_obj_from_request(request)
        if obj and obj.pk:
            if model is Patient and Observation.objects.filter(visit__patient__pk=obj.pk).count():
                return self.extra
            elif model is Visit and obj.observation.count():
                return self.extra

        center = Center.objects.get(pk=request.user.center.pk)
        query = Q(category=self.verbose_name.upper()) & (Q(center=center) | Q(center=None))
        return Observable.objects.filter(query).count()

    @classmethod
    def factory(cls):
        return [type(f"{x}ObservationInline", (cls,), dict(verbose_name=x.lower(),
                                                           verbose_name_plural=x.lower(),
                                                           classes=("collapse",))) for x in Observable.Category]


@admin.register(Observation)
class ObservationAdmin(ObservationMixin, RestrictedByCenterMixin, NestedModelAdmin):
    search_fields = ["observable__name", "visit__patient__patient_id", "visit__patient__patient_cid"]
    search_help_text = "Observable, Patient ID or CID"
    date_hierarchy = "updated_at"
    list_filter = ("visit__patient__center", "observable__category", "observable")
    list_display = ["patient_id", "observable_name", "visit"]


class ArrayDataMixin:
    ordering = ("-updated_at",)
    readonly_fields = ["created_at", "updated_at"]

    fieldsets = [
        (
            None,
            {
                "fields": ["instrument", "bio_sample", "data"]
            }
        ),
        (
            "Measurement Details",
            {
                "fields": ["measurement_id",
                           "measurement_type",
                           "acquisition_time",
                           "resolution",
                           "power",
                           "temperature",
                           "pressure",
                           "humidity",
                           "date"],
            }
        ),
        (
            "More Details",
            {
                "classes": ["collapse"],
                "fields": ["id", ("created_at", "updated_at")],
            }
        ),
    ]

    @admin.display
    def patient_id(self, obj):
        return obj.bio_sample.visit.patient_id

    def get_queryset(self, request):
        """ List only objects belonging to user's center. """
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        return qs.filter(bio_sample__visit__patient__center=Center.objects.get(pk=request.user.center.pk))


@admin.register(ArrayData)
class ArrayDataAdmin(ArrayDataMixin, RestrictedByCenterMixin, NestedModelAdmin):
    search_fields = ["bio_sample__visit__patient__patient_id", "bio_sample__visit__patient__patient_cid"]
    search_help_text = "Patient ID or CID"
    readonly_fields = ["created_at", "updated_at"]  # TODO: Might need specific user group.
    date_hierarchy = "updated_at"
    list_display = ["patient_id", "instrument", "data"]
    list_filter = ("bio_sample__visit__patient__center",
                   "instrument",
                   "measurement_type",
                   "bio_sample__sample_type",
                   "bio_sample__sample_processing",
                   "bio_sample__visit__observation__observable")


class ArrayDataAdminWithInlines(ArrayDataAdmin):
    inlines = [QCAnnotationInline]


class ArrayDataInline(ArrayDataMixin, RestrictedByCenterMixin, NestedStackedInline):
    model = ArrayData
    extra = 1
    min_num = 0
    show_change_link = True
    fk_name = "bio_sample"

    def get_extra(self, request, obj=None, **kwargs):
        # Only display inlines for those that exist, i.e., no expanded extras (if they exist).
        return 0 if obj and obj.pk and obj.array_data.count() else self.extra


class BioSampleMixin:
    readonly_fields = ["created_at", "updated_at"]  # TODO: Might need specific user group.
    ordering = ("-updated_at",)

    fieldsets = [
        (
            None,
            {
                "fields": ["visit"]
            }
        ),
        (
            "Sample Tagging",
            {
                "fields": [("sample_study_id", "sample_study_name", "sample_cid"),
                           "sample_type",
                           "sample_processing"]
            }
        ),
        (
            "Sample Extraction",
            {
                "fields": ["sample_extraction",
                           ("freezing_temp", "freezing_time"),
                           ("thawing_temp", "thawing_time"),
                           ("sample_extraction_tube", "centrifuge_rpm", "centrifuge_time")]
            }
        ),
        (
            "More Details",
            {
                "classes": ["collapse"],
                "fields": ["created_at", "updated_at"],
            }
        ),
    ]

    @admin.display
    def patient_id(self, obj):
        return obj.visit.patient_id

    def get_queryset(self, request):
        """ List only objects belonging to user's center. """
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        return qs.filter(visit__patient__center=Center.objects.get(pk=request.user.center.pk))


@admin.register(BioSample)
class BioSampleAdmin(BioSampleMixin, RestrictedByCenterMixin, NestedModelAdmin):
    search_fields = ["visit__patient__patient_id", "visit__patient__patient_cid"]
    search_help_text = "Patient ID or CID"
    date_hierarchy = "updated_at"
    list_filter = ("visit__patient__center", "sample_study_id", "sample_type", "sample_processing")
    list_display = ["patient_id", "sample_type"]


class BioSampleAdminWithInlines(BioSampleAdmin):
    inlines = [ArrayDataInline]


class BioSampleInline(BioSampleMixin, RestrictedByCenterMixin, NestedStackedInline):
    model = BioSample
    extra = 1
    min_num = 0
    show_change_link = True
    fk_name = "visit"
    inlines = [ArrayDataInline]

    def get_extra(self, request, obj=None, **kwargs):
        # Only display inlines for those that exist, i.e., no expanded extras (if they exist).
        return 0 if obj and obj.pk and obj.bio_sample.count() else self.extra


def get_obj_from_request(request):
    if not (object_id := request.resolver_match.kwargs.get("object_id", None)):
        return None, None

    # Parse the url_name and retrieve the model for the above object_id.
    try:
        app, model, action = request.resolver_match.url_name.split('_')
    except ValueError:  # too many values to unpack.
        return None, None

    try:
        model = apps.get_model(app, model)
    except LookupError:
        return None, None

    try:
        return model.objects.get(pk=object_id), model
    except ObjectDoesNotExist:
        return None, model


class VisitAdminMixin:
    readonly_fields = ["created_at", "updated_at"]  # TODO: Might need specific user group.
    ordering = ("-updated_at",)

    fieldsets = [
        (
            None,
            {
                "fields": ["patient", "days_observed"]
            }
        ),
        (
            "Advanced",
            {
                "classes": ["collapse"],
                "fields": ["previous_visit"],
            }
        ),
    ]

    @admin.display
    def patient_id(self, obj):
        return obj.patient.patient_id

    @admin.display
    def visit_count(self, obj):
        return Visit.objects.filter(patient=obj.patient).count()

    @admin.display
    def gender(self, obj):
        try:
            return obj.observation.get(observable__name="gender").observable_value
        except Observation.DoesNotExist:
            pass

    def get_queryset(self, request):
        """ List only objects belonging to user's center. """
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        return qs.filter(patient__center=Center.objects.get(pk=request.user.center.pk))

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        """ Limit previous_visit to user's center (super's functionality) and only those visits belonging to the same
            patient.
        """
        field = super().formfield_for_foreignkey(db_field, request, **kwargs)
        if db_field.name == "previous_visit":
            obj, model = get_obj_from_request(request)
            if obj is None:
                return field

            # Note: Our forms are RESTful and thus this still won't solve the situation where a new visit is
            #       added, a patient selected AND then have the previous_visit selection reduced based on the selected
            #       patient. The form knows nothing about the selected patient until posted.

            # Limit the QS for previous_visit.
            if model is Patient:
                # Limit to all visits belonging to this patient (inc self - unfortunatley. It would be better to
                # exclude (See below), however, there is no visit-self when looking at the patient level).
                field.queryset = field.queryset.filter(patient=obj)
            elif model is Visit:
                # Limit to all visits belonging to this patient (exc self - since a self-referential previous_visit
                # doesn't make much sense).
                patient = obj.patient
                field.queryset = field.queryset.filter(patient=patient).exclude(pk=obj.pk)
            else:
                return field

        return field


class VisitInline(VisitAdminMixin, RestrictedByCenterMixin, NestedTabularInline):
    model = Visit
    extra = 1
    min_num = 0
    show_change_link = True
    fk_name = "patient"
    inlines = [BioSampleInline, *ObservationInline.factory()]

    def get_extra(self, request, obj=None, **kwargs):
        # Only display inlines for those that exist, i.e., no expanded extras (if they exist).
        return 0 if obj and obj.pk and obj.visit.count() else self.extra


@admin.register(Visit)
class VisitAdmin(VisitAdminMixin, RestrictedByCenterMixin, NestedModelAdmin):
    search_fields = ["patient__patient_id", "patient__patient_cid"]
    search_help_text = "Patient ID or CID"
    date_hierarchy = "updated_at"
    list_filter = ("patient__center",)
    # autocomplete_fields = ["previous_visit"]  # Conflicts with VisitAdminForm queryset.
    list_display = ["patient_id", "visit_count", "gender"]


class VisitAdminWithInlines(VisitAdmin):
    inlines = [BioSampleInline, *ObservationInline.factory()]


@admin.register(Patient)
class PatientAdmin(RestrictedByCenterMixin, NestedModelAdmin):
    search_fields = ["patient_id", "patient_cid"]
    search_help_text = "Patient ID or CID"
    readonly_fields = ["created_at", "updated_at"]  # TODO: Might need specific user group.
    date_hierarchy = "updated_at"
    ordering = ("-updated_at",)
    list_filter = ("center", "visit__observation__observable")
    list_display = ["patient_id", "patient_cid", "gender", "age", "visit_count", "center"]

    @admin.display
    def age(self, obj):
        age = 0
        for visit in obj.visit.all():
            try:
                patient_age = int(visit.observation.get(observable__name="patient_age").observable_value)
            except Observation.DoesNotExist:
                continue
            else:
                age = max(age, patient_age)
        return age

    @admin.display
    def gender(self, obj):
        try:
            if visit := obj.visit.last():
                return visit.observation.get(observable__name="gender").observable_value
        except Observation.DoesNotExist:
            pass

    @admin.display
    def visit_count(self, obj):
        return obj.visit.count()

    def get_queryset(self, request):
        """ List only objects belonging to user's center. """
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        return qs.filter(center=Center.objects.get(pk=request.user.center.pk))


class PatientAdminWithInlines(PatientAdmin):
    inlines = [VisitInline]


@admin.register(Center)
class CenterAdmin(UserCenterAdmin):
    ...


class DataAdminSite(admin.AdminSite):
    site_header = settings.SITE_HEADER
    index_title = "Data Administration"
    site_title = index_title

    model_order = [Patient,
                   Visit,
                   Observation,
                   BioSample,
                   ArrayData,
                   UploadedFile
                   ]

    def get_app_list(self, request, app_label=None):
        app_list = super().get_app_list(request, app_label=app_label)

        if hasattr(self, "model_order"):
            for app in app_list:
                app["models"].sort(key=lambda x: self.model_order.index(x["model"]))

        return app_list


data_admin = DataAdminSite(name="data_admin")
data_admin.register(Patient, admin_class=PatientAdminWithInlines)
data_admin.register(Visit, admin_class=VisitAdminWithInlines)
data_admin.register(Observation, admin_class=ObservationAdmin)
data_admin.register(BioSample, admin_class=BioSampleAdminWithInlines)
data_admin.register(ArrayData, admin_class=ArrayDataAdminWithInlines)
data_admin.register(UploadedFile, admin_class=UploadedFileAdmin)
# data_admin.register(Instrument, admin_class=InstrumentAdmin)
# data_admin.register(QCAnnotation, admin_class=QCAnnotationAdmin)
# data_admin.register(QCAnnotator, admin_class=QCAnnotatorAdmin)
# data_admin.register(Observable, admin_class=ObservableAdmin)
