"""
Amina Stays API settings.

Everything secret or deployment-specific comes from the environment (.env at the repo
root or in backend/). Business settings Amina edits herself live in the database
(core.SiteSettings) and are managed from the host console.
"""

import os
import sys
from pathlib import Path

import dj_database_url
from django.core.exceptions import ImproperlyConfigured
from django.utils.csp import CSP
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
REPO_DIR = BASE_DIR.parent
load_dotenv(BASE_DIR / ".env")
load_dotenv(REPO_DIR / ".env")

TESTING = "pytest" in sys.modules or sys.argv[1:2] == ["test"]


def env(key, default=None):
    value = os.environ.get(key)
    return default if value is None or value.strip() == "" else value.strip()


def env_bool(key, default=False):
    value = env(key)
    return default if value is None else value.lower() in ("1", "true", "yes", "on")


def env_int(key, default):
    value = env(key)
    return default if value is None else int(value)


def env_list(key, default=""):
    return [item.strip() for item in (env(key) or default).split(",") if item.strip()]


DEBUG = env_bool("DEBUG", False)
DEV_SECRET = "dev-only-insecure-secret-key-change-me-before-deploying"
SECRET_KEY = env("SECRET_KEY", DEV_SECRET)
if SECRET_KEY == DEV_SECRET and not (DEBUG or TESTING):
    raise ImproperlyConfigured("Set SECRET_KEY in the environment (or DEBUG=1 for local development).")

ALLOWED_HOSTS = env_list("ALLOWED_HOSTS", "localhost,127.0.0.1,[::1],.ngrok-free.app,.ngrok.app,.trycloudflare.com")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.postgres",
    "rest_framework",
    "drf_spectacular",
    "corsheaders",
    "apps.core",
    "apps.accounts",
    "apps.properties",
    "apps.bookings",
    "apps.payments",
    "apps.messaging",
    "apps.comms",
    "apps.operations",
    "apps.safety",
    "apps.reviews",
    "apps.insights",
    "apps.support",
    "apps.guide",
    "apps.notices",
    "apps.rewards",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django.middleware.csp.ContentSecurityPolicyMiddleware",
]

ROOT_URLCONF = "config.urls"
APPEND_SLASH = False  # Africa's Talking and the Next.js proxy call exact paths; never redirect a POST

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASES = {
    "default": dj_database_url.parse(
        env("DATABASE_URL", "postgres://amina:amina@localhost:5432/amina"),
        conn_max_age=env_int("DB_CONN_MAX_AGE", 60),
        conn_health_checks=True,
    )
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# One cache for every process (web workers and the scheduler): the Daraja token (each new token invalidates the
# previous one), per-number login-code caps and login throttles. The table comes from core/0003; tests keep memory.
CACHES = {
    "default": (
        {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}
        if TESTING
        else {"BACKEND": "django.core.cache.backends.db.DatabaseCache", "LOCATION": "amina_cache"}
    )
}
AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en"
TIME_ZONE = "Africa/Nairobi"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
        if DEBUG or TESTING
        else "whitenoise.storage.CompressedManifestStaticFilesStorage"
    },
}
DATA_UPLOAD_MAX_MEMORY_SIZE = 8 * 1024 * 1024

# ---------- Sessions, CSRF, CORS ----------
# The Next.js app proxies /api/* to Django, so the browser sees one origin: session cookie + CSRF.
SESSION_COOKIE_AGE = 30 * 24 * 3600
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_HTTPONLY = False  # the SPA reads it and echoes it in X-CSRFToken
FRONTEND_URL = env("FRONTEND_URL", "http://localhost:3000").rstrip("/")
PUBLIC_URL = (env("PUBLIC_URL") or FRONTEND_URL).rstrip("/")
CSRF_TRUSTED_ORIGINS = sorted({FRONTEND_URL, PUBLIC_URL, *env_list("CSRF_TRUSTED_ORIGINS")})
CORS_ALLOWED_ORIGINS = sorted({FRONTEND_URL, *env_list("CORS_ALLOWED_ORIGINS")})
CORS_ALLOW_CREDENTIALS = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_HOST = True

if not DEBUG and not TESTING:
    SESSION_COOKIE_SECURE = env_bool("SECURE_COOKIES", True)
    CSRF_COOKIE_SECURE = env_bool("SECURE_COOKIES", True)
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
    SECURE_HSTS_SECONDS = env_int("SECURE_HSTS_SECONDS", 0)

# Django 6 built-in Content Security Policy (covers the Django admin and the API browser)
SECURE_CSP = {
    "default-src": [CSP.SELF],
    "img-src": [CSP.SELF, "data:", "https:"],
    "style-src": [CSP.SELF, CSP.UNSAFE_INLINE],
    "script-src": [CSP.SELF],
    "frame-ancestors": [CSP.NONE],
}

# ---------- REST framework ----------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework.authentication.SessionAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.AllowAny"],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"]
    + (["rest_framework.renderers.BrowsableAPIRenderer"] if DEBUG else []),
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "apps.core.api.exception_handler",
    "DEFAULT_THROTTLE_RATES": {
        "otp": "6/min",
        "otp_verify": "20/min",
        "anon": "300/min",
        "user": "1200/min",
        "webhook": "1200/min",
    },
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Amina Stays API",
    "DESCRIPTION": "Direct booking, guest communication (SMS, USSD, Voice, web) and host operations for Amina Stays.",
    "VERSION": "2.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
}

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"plain": {"format": "%(asctime)s %(levelname)s %(name)s: %(message)s"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "plain"}},
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {
        "django.db.backends": {"level": "WARNING"},
        "httpx": {"level": "WARNING"},
        "amina": {"level": env("LOG_LEVEL", "INFO"), "propagate": True},
    },
}

# ---------- Amina Stays / Africa's Talking ----------
AT_USERNAME = env("AT_USERNAME", "sandbox")
AT_API_KEY = env("AT_API_KEY", "")
AT_SANDBOX = AT_USERNAME.lower() == "sandbox"
AT_SENDER_ID = env("AT_SENDER_ID", "")  # registered alphanumeric sender ID or shortcode
AT_SMS_NUMBER = env("AT_SMS_NUMBER", "")  # "Ask Amina" two-way shortcode/number shown to guests
AT_USSD_CODE = env("AT_USSD_CODE", "")  # e.g. *384*1234#
AT_VOICE_NUMBER = env("AT_VOICE_NUMBER", "")  # "Call Amina" — Voice has no sandbox
AT_PAYMENT_PRODUCT = env("AT_PAYMENT_PRODUCT", "AminaStays")
AT_WHATSAPP_NUMBER = env("AT_WHATSAPP_NUMBER", "")  # AT Chat (preview) — international guests prefer WhatsApp
AT_DATA_PRODUCT = env("AT_DATA_PRODUCT", "")  # Mobile Data product: welcome, outage and reward bundles
AT_WEBHOOK_SECRET = env("AT_WEBHOOK_SECRET", "")  # if set, callbacks must carry it: /at/<secret>/… or ?key=<secret>
AT_HTTP_TIMEOUT = float(env("AT_HTTP_TIMEOUT", "10"))
GUIDE_REGION = env("GUIDE_REGION", "Kenya")  # added to local-guide map searches ("Fort Jesus, Old Town, Kenya")

# M-Pesa is off unless chosen: Daraja needs Safaricom's Go-Live first, so guests pay by card until then.
# AT's Payments product is no longer self-serve (onboarding-gated), so it is one provider of three.
MPESA_PROVIDER = (env("MPESA_PROVIDER", "off")).lower()  # off | simulate | daraja | africastalking
if MPESA_PROVIDER not in ("off", "simulate", "daraja", "africastalking"):
    raise ImproperlyConfigured("MPESA_PROVIDER must be off, simulate, daraja or africastalking.")
DARAJA_ENV = (env("DARAJA_ENV", "sandbox")).lower()  # sandbox | production
DARAJA_CONSUMER_KEY = env("DARAJA_CONSUMER_KEY", "")
DARAJA_CONSUMER_SECRET = env("DARAJA_CONSUMER_SECRET", "")
DARAJA_SHORTCODE = env("DARAJA_SHORTCODE", "174379")
DARAJA_PASSKEY = env("DARAJA_PASSKEY", "")
DARAJA_TRANSACTION_TYPE = env("DARAJA_TRANSACTION_TYPE", "CustomerPayBillOnline")  # CustomerBuyGoodsOnline = Till
if DARAJA_TRANSACTION_TYPE not in ("CustomerPayBillOnline", "CustomerBuyGoodsOnline"):
    raise ImproperlyConfigured(
        "DARAJA_TRANSACTION_TYPE must be CustomerPayBillOnline (Paybill) or CustomerBuyGoodsOnline (Till)."
    )
DARAJA_PARTY_B = env("DARAJA_PARTY_B", "")  # the Till number for CustomerBuyGoodsOnline ('' = DARAJA_SHORTCODE)
# Cards: Stripe Checkout as soon as its secret key is set; until then a simulated card page (the demo).
STRIPE_SECRET_KEY = env("STRIPE_SECRET_KEY", "")  # sk_test_… or sk_live_… (a restricted rk_… key works too)
STRIPE_WEBHOOK_SECRET = env("STRIPE_WEBHOOK_SECRET", "")  # whsec_…: instant confirmation (optional, recommended)
STRIPE_API_BASE = (env("STRIPE_API_BASE", "https://api.stripe.com")).rstrip("/")  # only tests point this elsewhere
CARD_PROVIDER = (env("CARD_PROVIDER", "stripe" if STRIPE_SECRET_KEY else "simulate")).lower()
if CARD_PROVIDER not in ("simulate", "stripe", "paystack"):
    raise ImproperlyConfigured("CARD_PROVIDER must be simulate, stripe or paystack.")
PAYSTACK_SECRET_KEY = env("PAYSTACK_SECRET_KEY", "")
SIM_PAY_DELAY_SECONDS = float(env("SIM_PAY_DELAY_SECONDS", "6"))
SIM_SWAP_PROVIDER = (env("SIM_SWAP_PROVIDER", "")).lower()  # africastalking | simulate ('' = auto)

LOCK_PROVIDER_API_BASE = env("IGLOOHOME_API_BASE", "")
IGLOOHOME_API_KEY = env("IGLOOHOME_API_KEY", "")

AMINA_PHONE = env("AMINA_PHONE", "+254700000001")
# Guest phones used in Africa's Talking's simulator: seed_demo makes them real guests (their SMS really go out)
SIMULATOR_GUESTS = env_list("SIMULATOR_GUESTS")
BACKEND_URL = (env("BACKEND_URL", "http://127.0.0.1:8000")).rstrip("/")
DEMO = env_bool("DEMO", False)
OUTBOX_MODE = env("OUTBOX_MODE", "sync" if TESTING else "thread")  # thread | sync | queue
ID_ENCRYPTION_KEY = env("ID_ENCRYPTION_KEY", "")
SCHEDULER_INTERVAL_SECONDS = env_int("SCHEDULER_INTERVAL_SECONDS", 30)
