"""
Django settings for Fuel Route Optimizer API.
Configured as a lightweight, stateless REST microservice.
"""

from pathlib import Path
import os

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.getenv("SECRET_KEY", "django-insecure-spotter-dev-key-change-in-production")

DEBUG = os.getenv("DEBUG", "True").lower() in ("true", "1", "t")

ALLOWED_HOSTS = os.getenv("ALLOWED_HOSTS", "*").split(",")

INSTALLED_APPS = [
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.staticfiles',
    
    # Third-party packages
    'rest_framework',
    'corsheaders',

    # Domain application
    'fuel_router.apps.FuelRouterConfig',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
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

AUTH_PASSWORD_VALIDATORS = []

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
STATICFILES_DIRS = [BASE_DIR / 'static'] if (BASE_DIR / 'static').exists() else []

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

CORS_ALLOW_ALL_ORIGINS = True

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [],
    'DEFAULT_PERMISSION_CLASSES': [],
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
        'rest_framework.renderers.BrowsableAPIRenderer',
    ],
}

CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'fuel-route-cache',
    }
}
CACHE_TTL_SECONDS = int(os.getenv("CACHE_TTL_SECONDS", "3600"))

# Routing & Optimization Configurations
ROUTING_SERVICE_URL = os.getenv("ROUTING_SERVICE_URL", "https://router.project-osrm.org")
GEOCODING_SERVICE_URL = os.getenv("GEOCODING_SERVICE_URL", "https://nominatim.openstreetmap.org/search")
GEOCODING_USER_AGENT = os.getenv("GEOCODING_USER_AGENT", "FuelRouterApp/1.0 (contact: admin@fuelrouter.local)")

ROUTING_TIMEOUT_SECONDS = int(os.getenv("ROUTING_TIMEOUT_SECONDS", "10"))
GEOCODING_TIMEOUT_SECONDS = int(os.getenv("GEOCODING_TIMEOUT_SECONDS", "5"))
ROUTE_SAMPLING_STEP_MILES = float(os.getenv("ROUTE_SAMPLING_STEP_MILES", "35.0"))
ROUTE_SEARCH_RADIUS_MILES = float(os.getenv("ROUTE_SEARCH_RADIUS_MILES", "15.0"))

VEHICLE_MAX_RANGE_MILES = 500.0
VEHICLE_MPG = 10.0
METERS_TO_MILES = 0.000621371

