# findam/settings.py
# Configuration principale du projet Django Findam - Version simplifiée

import os
from pathlib import Path
from datetime import timedelta

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = 'django-insecure-temporary-key-for-dev'

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

ALLOWED_HOSTS = ['*']

CSRF_TRUSTED_ORIGINS = ['https://46c4-2c0f-2a80-946-a310-fd24-69b5-e807-2268.ngrok-free.app', 'http://localhost:3000', 'http://localhost:8000']


# Application definition

DJANGO_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
]

THIRD_PARTY_APPS = [
    'channels',
    'rest_framework',
    'corsheaders',
    'rest_framework_simplejwt',
    'django_crontab',
]

LOCAL_APPS = [
    'accounts',
    'properties',
    'bookings.apps.BookingsConfig',
    'communications',
    'payments.apps.PaymentsConfig',
    'reviews',
    'common',
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'bookings.signals.BookingStatusMiddleware',
]

ROOT_URLCONF = 'findam.urls'

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

WSGI_APPLICATION = 'findam.wsgi.application'
ASGI_APPLICATION = 'findam.asgi.application'

CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels.layers.InMemoryChannelLayer',
    },
}

# Database
# https://docs.djangoproject.com/en/4.2/ref/settings/#databases

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': os.path.join(BASE_DIR, 'db.sqlite3'),
    }
}

# Pour utiliser PostgreSQL, décommentez et configurez les lignes suivantes :
# DATABASES = {
#     'default': {
#         'ENGINE': 'django.db.backends.postgresql',
#         'NAME': 'findam',
#         'USER': 'postgres',
#         'PASSWORD': 'votre_mot_de_passe',
#         'HOST': 'localhost',
#         'PORT': '5432',
#     }
# }

# Password validation
# https://docs.djangoproject.com/en/4.2/ref/settings/#auth-password-validators

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


# Internationalization
# https://docs.djangoproject.com/en/4.2/topics/i18n/

LANGUAGE_CODE = 'fr-fr'  # Langue par défaut pour le Cameroun

TIME_ZONE = 'Africa/Douala'  # Fuseau horaire du Cameroun

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/4.2/howto/static-files/

STATIC_URL = 'static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'static_collected')
STATICFILES_DIRS = [os.path.join(BASE_DIR, 'static')]

# Media files
MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

# Default primary key field type
# https://docs.djangoproject.com/en/4.2/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Configuration Utilisateur personnalisé
AUTH_USER_MODEL = 'accounts.User'

# Configuration DRF
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.AllowAny',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 10,
    'DEFAULT_SCHEMA_CLASS': 'rest_framework.schemas.coreapi.AutoSchema',
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle'
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '1000/day',
        'user': '5000/day'
    }
}

# Configuration JWT
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(hours=1),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=1),
    'ROTATE_REFRESH_TOKENS': False,
    'BLACKLIST_AFTER_ROTATION': True,
    'UPDATE_LAST_LOGIN': False,

    'ALGORITHM': 'HS256',
    'SIGNING_KEY': SECRET_KEY,
    'VERIFYING_KEY': None,
    'AUDIENCE': None,
    'ISSUER': None,

    'AUTH_HEADER_TYPES': ('Bearer',),
    'AUTH_HEADER_NAME': 'HTTP_AUTHORIZATION',
    'USER_ID_FIELD': 'id',
    'USER_ID_CLAIM': 'user_id',

    'AUTH_TOKEN_CLASSES': ('rest_framework_simplejwt.tokens.AccessToken',),
    'TOKEN_TYPE_CLAIM': 'token_type',

    'JTI_CLAIM': 'jti',

    'SLIDING_TOKEN_REFRESH_EXP_CLAIM': 'refresh_exp',
    'SLIDING_TOKEN_LIFETIME': timedelta(minutes=5),
    'SLIDING_TOKEN_REFRESH_LIFETIME': timedelta(days=1),
}

# Configuration CORS
CORS_ALLOW_ALL_ORIGINS = True  # Permettre à tous les domaines en développement
# Pour la production, utilisez plutôt:
# CORS_ALLOW_ALL_ORIGINS = False
# CORS_ALLOWED_ORIGINS = [
#     'http://localhost:3000',
#     'http://127.0.0.1:3000',
#     'votre-domaine-production.com',
# ]

# Configurez également CORS pour les WebSockets
CORS_ALLOW_CREDENTIALS = True

# Sécurité supplémentaire (désactivées en développement)
SECURE_BROWSER_XSS_FILTER = False
SECURE_CONTENT_TYPE_NOSNIFF = False
X_FRAME_OPTIONS = 'SAMEORIGIN'

# Configurations des emails (utilise la console en développement)
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
DEFAULT_FROM_EMAIL = 'noreply@findam.com'

# Pour la configuration d'emails en production, décommentez et configurez:
# EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
# EMAIL_HOST = 'smtp.gmail.com'  # Par exemple pour Gmail
# EMAIL_PORT = 587
# EMAIL_USE_TLS = True
# EMAIL_HOST_USER = 'votre-email@gmail.com'
# EMAIL_HOST_PASSWORD = 'votre-mot-de-passe'

# Configuration NotchPay (pour les paiements)
NOTCHPAY_PUBLIC_KEY = 'pk_test.hlN4xPJaXIjZOGJLYtNrr65J1eJ0lNu0X9QLYtcPbRf03ox9cgt5nCOBdBuafwsgUjWsmgb8zTcFPVXiEWKHeR2A6l3xdGZIpVBy7xKREnUhnAC6u9M2YLRaGOhUA'
NOTCHPAY_PRIVATE_KEY = 'sk_test.iL0dqwKw4ssMOAArlzFDBkARtijZBD5pXU8SHJ1jd6jaTpqIfjP7tiEoaTBbzbmbKp1Kne154FdDtjD2HXIN9sDq7ksmQQ6EeUHPO93pYj5Cu3eql9JqzJISaBo1z'
NOTCHPAY_HASH_KEY = 'hsk_test.NThcqZtbkPucsO63CdIwyyvix5U9I4BVShvDdbLkLxa58Kd3rl7ifoN17Cx8Dklj2umRE2WtM2HTo6lWFILUzNj9OoF3RIy5LIvapbVHYuvGuQxjK5ID52yh83Itt'

NOTCHPAY_SANDBOX = True  # Définir sur False en production

# URL base pour les callbacks de paiement
PAYMENT_CALLBACK_BASE_URL = 'https://46c4-2c0f-2a80-946-a310-fd24-69b5-e807-2268.ngrok-free.app'  # Domaine pour les callbacks de production

# En développement, utilisez ngrok ou un service similaire pour recevoir les webhooks
if DEBUG:
    PAYMENT_CALLBACK_BASE_URL = 'https://46c4-2c0f-2a80-946-a310-fd24-69b5-e807-2268.ngrok-free.app'  # Remplacer par votre URL ngrok en développement

# URL du frontend pour les redirections
FRONTEND_URL = 'http://localhost:3000'  # URL du frontend en développement

# En production, on utiliserait le même domaine que l'API
if not DEBUG:
    FRONTEND_URL = 'https://votre-domaine.com'  # À adapter en production

# Configuration des tâches planifiées
CRONJOBS = [
    ('0 */4 * * *', 'payments.tasks.schedule_payouts_for_new_bookings'),  # Toutes les 4 heures
    ('0 */2 * * *', 'payments.tasks.process_scheduled_payouts'),          # Toutes les 2 heures
    ('0 */3 * * *', 'payments.tasks.process_ready_payouts'),              # Toutes les 3 heures
    ('0 12 * * *', 'payments.tasks.check_pending_checkins'),              # Tous les jours à midi
]

GOOGLE_OAUTH_CLIENT_ID = '981620828584-2sjvn5tcn2ekitpthias8h0tj1h6dkts.apps.googleusercontent.com'
GOOGLE_OAUTH_CLIENT_SECRET = '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'
GOOGLE_OAUTH_REDIRECT_URI = 'http://localhost:8000/api/v1/auth/google/callback/'

FACEBOOK_APP_ID = 'votre_app_id_facebook'
FACEBOOK_APP_SECRET = 'votre_app_secret_facebook'
FACEBOOK_REDIRECT_URI = 'http://localhost:8000/api/v1/auth/facebook/callback/'

# Configuration de logging
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {
            'level': 'DEBUG',
            'class': 'logging.StreamHandler',
        },
        'file': {
            'level': 'WARNING',
            'class': 'logging.FileHandler',
            'filename': os.path.join(BASE_DIR, 'logs/findam.log'),
        },
    },
    'loggers': {
        'django': {
            'handlers': ['console', 'file'],
            'level': 'INFO',
            'propagate': True,
        },
        'findam': {
            'handlers': ['console', 'file'],
            'level': 'DEBUG',
            'propagate': True,
        },
    },
}

# Assurez-vous que le dossier logs existe
os.makedirs(os.path.join(BASE_DIR, 'logs'), exist_ok=True)