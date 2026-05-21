import os
from datetime import timedelta
from pathlib import Path

import environ
from celery.schedules import crontab

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env()
environ.Env.read_env(os.path.join(BASE_DIR, '.env'))

SECRET_KEY = env('SECRET_KEY', default='unsafe-secret-key')

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # Third Party
    'rest_framework',
    'corsheaders',
    'django_filters',
    'rest_framework_simplejwt',
    'drf_spectacular',

    # Local Apps
    'apps.users.apps.UsersConfig',
    'apps.documents.apps.DocumentsConfig',
    'apps.processing.apps.ProcessingConfig',
    'apps.datasets.apps.DatasetsConfig',
    'apps.marketplace.apps.MarketplaceConfig',
    'apps.scoring.apps.ScoringConfig',
    'apps.payments.apps.PaymentsConfig',
    'apps.notifications.apps.NotificationsConfig',
    'apps.common.apps.CommonConfig',
    'apps.nlp.apps.NlpConfig',
    'apps.analytics.apps.AnalyticsConfig',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [os.path.join(BASE_DIR, 'templates')],
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

WSGI_APPLICATION = 'config.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    'DEFAULT_FILTER_BACKENDS': ['django_filters.rest_framework.DjangoFilterBackend'],
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
}

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=60),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': False,
    'UPDATE_LAST_LOGIN': True,

    'ALGORITHM': 'HS256',
    'SIGNING_KEY': SECRET_KEY,
    'VERIFYING_KEY': None,
    'AUDIENCE': None,
    'ISSUER': None,
    'JSON_ENCODER': None,
    'JWK_URL': None,
    'LEEWAY': 0,

    'AUTH_HEADER_TYPES': ('Bearer',),
    'AUTH_HEADER_NAME': 'HTTP_AUTHORIZATION',
    'USER_ID_FIELD': 'id',
    'USER_ID_CLAIM': 'user_id',
    'USER_AUTHENTICATION_RULE': 'rest_framework_simplejwt.authentication.default_user_authentication_rule',

    'AUTH_TOKEN_CLASSES': ('rest_framework_simplejwt.tokens.AccessToken',),
    'TOKEN_TYPE_CLAIM': 'token_type',
    'TOKEN_USER_CLASS': 'rest_framework_simplejwt.models.TokenUser',

    'JTI_CLAIM': 'jti',

    'SLIDING_TOKEN_REFRESH_EXP_CLAIM': 'refresh_exp',
    'SLIDING_TOKEN_LIFETIME': timedelta(minutes=5),
    'SLIDING_TOKEN_REFRESH_LIFETIME': timedelta(days=1),
}

SPECTACULAR_SETTINGS = {
    'TITLE': 'FidelAI API',
    'DESCRIPTION': 'AI-driven Amharic data marketplace and crowdsourcing platform API',
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
    'COMPONENT_SPLIT_REQUEST': True,
}

AUTH_USER_MODEL = 'users.CustomUser'

CELERY_BROKER_URL = env('REDIS_URL', default='redis://localhost:6379/1')
CELERY_PROCESSING_BATCH_SIZE = env.int('CELERY_PROCESSING_BATCH_SIZE', default=25)
CELERY_CHUNKING_BATCH_SIZE = env.int('CELERY_CHUNKING_BATCH_SIZE', default=25)
CELERY_TASK_CREATION_BATCH_SIZE = env.int('CELERY_TASK_CREATION_BATCH_SIZE', default=25)
CELERY_MAX_CHUNKS_PER_TASK = env.int('CELERY_MAX_CHUNKS_PER_TASK', default=30)
CELERY_CONSENSUS_BATCH_SIZE = env.int('CELERY_CONSENSUS_BATCH_SIZE', default=100)
CELERY_EXPERT_TASK_BATCH_SIZE = env.int('CELERY_EXPERT_TASK_BATCH_SIZE', default=100)
CELERY_EXPERT_TASK_ASSIGNMENT_BATCH_SIZE = env.int('CELERY_EXPERT_TASK_ASSIGNMENT_BATCH_SIZE', default=50)
CELERY_NLP_CANDIDATE_EXTRACTION_BATCH_SIZE = env.int('CELERY_NLP_CANDIDATE_EXTRACTION_BATCH_SIZE', default=50)
CELERY_NLP_CONSENSUS_BATCH_SIZE = env.int('CELERY_NLP_CONSENSUS_BATCH_SIZE', default=100)
CELERY_DATASET_AGGREGATION_TITLE = env('CELERY_DATASET_AGGREGATION_TITLE', default='Auto-built NLP dataset')
CELERY_DATASET_AGGREGATION_DESCRIPTION = env(
    'CELERY_DATASET_AGGREGATION_DESCRIPTION',
    default='Periodically aggregated dataset from approved NLP consensus results',
)
CELERY_DATASET_AGGREGATION_TASK_TYPE = env('CELERY_DATASET_AGGREGATION_TASK_TYPE', default='sentiment')
CELERY_DATASET_AGGREGATION_DOMAINS = env('CELERY_DATASET_AGGREGATION_DOMAINS', default='')
CELERY_DATASET_AGGREGATION_MIN_AGREEMENT_SCORE = env.float(
    'CELERY_DATASET_AGGREGATION_MIN_AGREEMENT_SCORE',
    default=0.8,
)
CELERY_DATASET_AGGREGATION_MAX_EXAMPLES = env.int('CELERY_DATASET_AGGREGATION_MAX_EXAMPLES', default=15000)
CELERY_DATASET_AGGREGATION_BALANCE_LABELS = env.bool('CELERY_DATASET_AGGREGATION_BALANCE_LABELS', default=True)
CELERY_DATASET_AGGREGATION_LICENSE_TYPE = env('CELERY_DATASET_AGGREGATION_LICENSE_TYPE', default='mit')
CELERY_DATASET_AGGREGATION_PRICE = env.float('CELERY_DATASET_AGGREGATION_PRICE', default=0.0)
CELERY_BEAT_SCHEDULE = {
    'dispatch-pending-document-processing': {
        'task': 'apps.processing.tasks.DispatchPendingDocumentProcessing',
        'schedule': crontab(minute='*/1'),
        'args': (CELERY_PROCESSING_BATCH_SIZE,),
    },
    'dispatch-pending-chunking': {
        'task': 'apps.processing.tasks.DispatchPendingChunking',
        'schedule': crontab(minute='*/1'),
        'args': (CELERY_CHUNKING_BATCH_SIZE,),
    },
    'dispatch-pending-task-creation': {
        'task': 'apps.processing.tasks.DispatchPendingTaskCreation',
        'schedule': crontab(minute='*/1'),
        'args': (CELERY_TASK_CREATION_BATCH_SIZE, CELERY_MAX_CHUNKS_PER_TASK),
    },
    'dispatch-pending-task-assignments': {
        'task': 'apps.processing.tasks.DispatchPendingTaskAssignments',
        'schedule': crontab(minute='*/5'),
    },
    'dispatch-pending-consensus': {
        'task': 'apps.processing.tasks.DispatchPendingConsensus',
        'schedule': crontab(minute='*/2'),
        'args': (CELERY_CONSENSUS_BATCH_SIZE,),
    },
    'dispatch-pending-expert-tasks': {
        'task': 'apps.processing.tasks.DispatchPendingExpertTasks',
        'schedule': crontab(minute='*/2'),
        'args': (CELERY_EXPERT_TASK_BATCH_SIZE, 10),
    },
    'dispatch-pending-expert-task-assignments': {
        'task': 'apps.processing.tasks.DispatchPendingExpertTaskAssignments',
        'schedule': crontab(minute='*/5'),
        'args': (CELERY_EXPERT_TASK_ASSIGNMENT_BATCH_SIZE,),
    },
    'dispatch-pending-nlp-candidate-extraction': {
        'task': 'apps.nlp.tasks.DispatchPendingNlpCandidateExtraction',
        'schedule': crontab(minute='*/5'),
        'args': (CELERY_NLP_CANDIDATE_EXTRACTION_BATCH_SIZE,),
    },
    'dispatch-nlp-task-creation': {
        'task': 'apps.nlp.tasks.DispatchNlpTaskCreation',
        'schedule': crontab(minute='*/2'),
    },
    'dispatch-nlp-task-assignment': {
        'task': 'apps.nlp.tasks.DispatchNlpTaskAssignment',
        'schedule': crontab(minute='*/5'),
    },
    'dispatch-nlp-consensus': {
        'task': 'apps.nlp.tasks.DispatchNlpConsensus',
        'schedule': crontab(minute='*/5'),
        'args': (CELERY_NLP_CONSENSUS_BATCH_SIZE,),
    },
    'dispatch-dataset-aggregation': {
        'task': 'apps.datasets.tasks.DispatchDatasetAggregation',
        'schedule': crontab(hour='*/6', minute=0),
        'args': (
            CELERY_DATASET_AGGREGATION_TITLE,
            CELERY_DATASET_AGGREGATION_DESCRIPTION,
            CELERY_DATASET_AGGREGATION_TASK_TYPE,
            CELERY_DATASET_AGGREGATION_DOMAINS,
            CELERY_DATASET_AGGREGATION_MIN_AGREEMENT_SCORE,
            CELERY_DATASET_AGGREGATION_MAX_EXAMPLES,
            CELERY_DATASET_AGGREGATION_BALANCE_LABELS,
            None,
            CELERY_DATASET_AGGREGATION_LICENSE_TYPE,
            CELERY_DATASET_AGGREGATION_PRICE,
        ),
    },
}

EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = "smtp.gmail.com"
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = env('EMAIL_USER')
EMAIL_HOST_PASSWORD = env('EMAIL_PASS')
DEFAULT_FROM_EMAIL = EMAIL_HOST_USER

FRONTEND_URL = env('FRONTEND_URL', default='http://localhost:3000')
CHAPA_SECRET_KEY = env('CHAPA_SECRET_KEY', default='')
CHAPA_BASE_URL = env('CHAPA_BASE_URL', default='https://api.chapa.co/v1')
CHAPA_DEFAULT_CURRENCY = env('CHAPA_DEFAULT_CURRENCY', default='ETB')

STATIC_URL = '/static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'static')
MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')
