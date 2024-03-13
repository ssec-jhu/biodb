"""
Django settings for biospecdb project.

Generated by 'django-admin startproject' using Django 4.1.

For more information on this file, see
https://docs.djangoproject.com/en/4.1/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/4.1/ref/settings/
"""

import os
from pathlib import Path
import sys

from biospecdb import __project__

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent.parent
PROJECT_ROOT = BASE_DIR / __project__
APPS_DIR = PROJECT_ROOT / 'apps'
sys.path.insert(0, str(APPS_DIR))

# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/4.1/howto/deployment/checklist/

# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    "storages",
    "nested_admin",
    "explorer",
    "uploader.apps.UploaderConfig",
    "user.apps.UserConfig",
    "catalog.apps.CatalogConfig",
    "health_check",
    "health_check.db",
    "health_check.cache",
    "health_check.storage",
    "health_check.contrib.migrations",
    "django_crontab"
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    "whitenoise.middleware.WhiteNoiseMiddleware",
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

AUTH_USER_MODEL = "user.User"

ROOT_URLCONF = 'biospecdb.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'biospecdb.wsgi.application'

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{name} {asctime} {levelname} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "WARNING",
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": os.getenv("DJANGO_LOG_LEVEL", "INFO"),
            "propagate": False,
        },
    },
}


# Database
# https://docs.djangoproject.com/en/4.1/ref/settings/#databases
db_vendor = os.getenv("DB_VENDOR", "sqlite")

if db_vendor == "sqlite":
    DB_DIR = "db"
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / DB_DIR / 'admin.sqlite3',
        },
        "bsr": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / DB_DIR / "bsr.sqlite3",
        }
    }
elif db_vendor == "postgresql":
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': 'admin',
            "HOST": os.getenv("DB_ADMIN_HOST"),
            "PORT": os.getenv("DB_ADMIN_PORT"),
            "USER": os.getenv("DB_ADMIN_USER"),
            "PASSWORD": os.getenv("DB_ADMIN_PASSWORD"),
        },
        "bsr": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": "bsr",
            "HOST": os.getenv("DB_BSR_HOST"),
            "PORT": os.getenv("DB_BSR_PORT"),
            "USER": os.getenv("DB_BSR_USER"),
            "PASSWORD": os.getenv("DB_BSR_PASSWORD"),
        },
        "bsr_readonly": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": "bsr",
            "HOST": os.getenv("DB_BSR_HOST"),
            "PORT": os.getenv("DB_BSR_PORT"),
            "USER": os.getenv("DB_BSR_USER"),
            "PASSWORD": os.getenv("DB_BSR_PASSWORD"),
            'OPTIONS': {
                'options': '-c default_transaction_read_only=on'
            }
        }
    }
else:
    raise NotImplementedError


# The order in which routers are processed is significant. Routers will be queried in the order they are listed here.
DATABASE_ROUTERS = ["biospecdb.routers.BSRRouter"]


# Password validation
# https://docs.djangoproject.com/en/4.1/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

HOST_DOMAIN = os.getenv("HOST_DOMAIN")

LOGIN_URL = "/admin/login"
LOGOUT_URL = "logout"

# Email settings
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = "smtp.sendgrid.net"
EMAIL_USE_TLS = True
EMAIL_PORT = 587
EMAIL_HOST_USER = "apikey"  # this is exactly the value 'apikey', this is NOT a placeholder.
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_API_KEY", None)
EMAIL_FROM = f"admin@{HOST_DOMAIN}"
EMAIL_SUBJECT_PREFIX = "SPaDDa"

# Internationalization
# https://docs.djangoproject.com/en/4.1/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'EST'

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/4.1/howto/static-files/

STATIC_ROOT = BASE_DIR / "static/"
STATICFILES_DIRS = [APPS_DIR / "uploader/templates/static"]
STATIC_URL = "/static/"

# Default primary key field type
# https://docs.djangoproject.com/en/4.1/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'


# SQL explorer settings.
if db_vendor == "postgresql":
    EXPLORER_CONNECTIONS = {"data": "bsr_readonly"}
    EXPLORER_DEFAULT_CONNECTION = "bsr_readonly"
else:
    EXPLORER_CONNECTIONS = {"data": "bsr"}
    EXPLORER_DEFAULT_CONNECTION = "bsr"

EXPLORER_PERMISSION_VIEW = lambda r: r.user.is_sqluser or r.user.is_superuser  # noqa:  E731
EXPLORER_PERMISSION_CHANGE = lambda r: r.user.is_superuser  # noqa:  E731

EXPLORER_DEFAULT_ROWS = 1000

EXPLORER_SQL_BLACKLIST = (
     # DML
     'COMMIT',
     'DELETE',
     'INSERT',
     'MERGE',
     'REPLACE',
     'ROLLBACK',
     'SET',
     'START',
     'UPDATE',
     'UPSERT',

     # DDL
     'ALTER',
     'CREATE',
     'DROP',
     'RENAME',
     'TRUNCATE',

     # DCL
     'GRANT',
     'REVOKE',
 )

EXPLORER_SCHEMA_EXCLUDE_TABLE_PREFIXES = (
    'auth',
    'contenttypes',
    'sessions',
    'admin',
    "django",
    "explorer",
    "user",
    "catalog",
    "uploader_center",
    "health_check",
    "whitenoise"
)

EXPLORER_DATA_EXPORTERS = [
    ('csv', 'uploader.exporters.CSVExporter'),
    ('excel', 'uploader.exporters.ExcelExporter'),
    ('json', 'uploader.exporters.JSONExporter')
]

EXPLORER_SCHEMA_INCLUDE_VIEWS = True

EXPLORER_CHARTS_ENABLED = True

# NOTE: The following two settings don't actually belong to explorer.

# Include the spectral data files, if present in query results, for download as zip file.
EXPLORER_DATA_EXPORTERS_INCLUDE_DATA_FILES = True
# Exhaustively scan query result values for relevant filepaths to collect data files. Does nothing when
# EXPLORER_DATA_EXPORTERS_INCLUDE_DATA_FILES == False.
EXPLORER_DATA_EXPORTERS_ALLOW_DATA_FILE_ALIAS = False

# Custom settings:

# Automatically run "default" annotators when new spectral data is saved. Note: Annotators are always run when new
# annotations are explicitly created and saved regardless of the below setting.
AUTO_ANNOTATE = True

# Run newly added/updated annotator on all spectral data if annotator.default is True.
# WARNING: This may be time-consuming if the annotators takes a while to run and there are a lot of
# spectral data samples in the database.
RUN_DEFAULT_ANNOTATORS_WHEN_SAVED = False

# Disable this class for now as #69 made it obsolete, however, there's a very good chance it will be needed
# when implementing background tasks for https://github.com/rispadd/biospecdb/pull/77.
DISABLE_QC_MANAGER = True

# Auto-populate the model field ``Visit.previous_visit`` by searching for existing older visits and choosing the last.
# WARNING! This may give incorrect results, e.g., when retrospectively adding prior visits.
AUTO_FIND_PREVIOUS_VISIT = False

# Data Catalog settings:

DATASET_CATALOG_FILE_CLASS = "uploader.exporters.CSVExporter"

# For options see https://docs.python.org/3/library/zipfile.html#zipfile.ZIP_STORED
ZIP_COMPRESSION = "zipfile.ZIP_DEFLATED"

# For options see https://docs.python.org/3/library/zlib.html#zlib.compressobj
ZIP_COMPRESSION_LEVEL = -1

CRONJOBS = [
    ("0 0 * * *", "django.core.management.call_command", ["prune_files"]),  # Every day at 12am (00:00).
]
