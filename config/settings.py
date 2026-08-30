from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent
env = environ.Env(DEBUG=(bool, True))
environ.Env.read_env(BASE_DIR / ".env")
SECRET_KEY = env("SECRET_KEY", default="dev-only-change-me")
DEBUG = env.bool("DEBUG", default=True)
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["127.0.0.1", "localhost"])
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "accounts",
    "core",
    "subscriptions",
    "payments",
    "downloads",
    "licenses",
    "support",
    "audit",
    "dashboard",
    "api",
]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
ROOT_URLCONF = "config.urls"
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "core.context_processors.site_context",
            ]
        },
    }
]
WSGI_APPLICATION = "config.wsgi.application"
DATABASES = {"default": env.db("DATABASE_URL", default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}")}
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
LANGUAGE_CODE, TIME_ZONE, USE_I18N, USE_TZ = "pt-br", "America/Sao_Paulo", True, True
STATIC_URL, STATIC_ROOT, STATICFILES_DIRS = "/static/", BASE_DIR / "staticfiles", [BASE_DIR / "static"]
MEDIA_URL = "/media/"
MEDIA_ROOT = Path(env("MEDIA_ROOT", default=str(BASE_DIR / "media")))
STATIC_BACKEND = (
    "whitenoise.storage.CompressedManifestStaticFilesStorage"
    if not DEBUG
    else "django.contrib.staticfiles.storage.StaticFilesStorage"
)
DOWNLOAD_STORAGE = env("DOWNLOAD_STORAGE", default="local").lower()
if DOWNLOAD_STORAGE == "s3":
    DEFAULT_STORAGE = {
        "BACKEND": "storages.backends.s3.S3Storage",
        "OPTIONS": {
            "access_key": env("AWS_ACCESS_KEY_ID"),
            "secret_key": env("AWS_SECRET_ACCESS_KEY"),
            "bucket_name": env("AWS_STORAGE_BUCKET_NAME"),
            "endpoint_url": env("AWS_S3_ENDPOINT_URL", default=None),
            "region_name": env("AWS_S3_REGION_NAME", default=None),
            "default_acl": "private",
            "querystring_auth": True,
            "file_overwrite": False,
        },
    }
else:
    DEFAULT_STORAGE = {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
        "OPTIONS": {"location": MEDIA_ROOT, "base_url": MEDIA_URL},
    }

STORAGES = {
    "staticfiles": {"BACKEND": STATIC_BACKEND},
    "default": DEFAULT_STORAGE,
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
AUTH_USER_MODEL = "accounts.User"
LOGIN_URL, LOGIN_REDIRECT_URL, LOGOUT_REDIRECT_URL = "accounts:login", "dashboard:home", "core:home"
EMAIL_BACKEND = env("EMAIL_BACKEND", default="django.core.mail.backends.console.EmailBackend")
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="RoadLedger <no-reply@roadledger.local>")
SITE_URL = env("SITE_URL", default="http://127.0.0.1:8000")
MP_ENVIRONMENT = env("MP_ENVIRONMENT", default="sandbox")
MP_PUBLIC_KEY = env("MP_PUBLIC_KEY", default="")
MP_ACCESS_TOKEN = env("MP_ACCESS_TOKEN", default="")
MP_CLIENT_ID = env("MP_CLIENT_ID", default="")
MP_CLIENT_SECRET = env("MP_CLIENT_SECRET", default="")
MP_WEBHOOK_SECRET = env("MP_WEBHOOK_SECRET", default="")
MP_WEBHOOK_URL = env("MP_WEBHOOK_URL", default=f"{SITE_URL}/pagamentos/webhook/mercado-pago/")
PAYMENT_CREDENTIALS_KEY = env("PAYMENT_CREDENTIALS_KEY", default=SECRET_KEY)
SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=False)
SECURE_HSTS_SECONDS = env.int("SECURE_HSTS_SECONDS", default=0)
SECURE_HSTS_INCLUDE_SUBDOMAINS = env.bool("SECURE_HSTS_INCLUDE_SUBDOMAINS", default=False)
SECURE_HSTS_PRELOAD = env.bool("SECURE_HSTS_PRELOAD", default=False)
SESSION_COOKIE_SECURE = env.bool("SESSION_COOKIE_SECURE", default=not DEBUG)
CSRF_COOKIE_SECURE = env.bool("CSRF_COOKIE_SECURE", default=not DEBUG)
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True
