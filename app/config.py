import datetime
import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
INSTANCE_DIR = BASE_DIR / "instance"
INSTANCE_DIR.mkdir(exist_ok=True)
INVALID_GEMINI_KEY_VALUES = {
    "",
    "your-gemini-api-key-here",
    "replace-with-your-gemini-key",
    "replace-me",
    "changeme",
    "demo-key",
}
INVALID_SECRET_KEY_VALUES = {
    "",
    "change-this-in-production",
    "dev-only-secret-key",
    "replace-with-a-secure-secret",
}
INVALID_MAIL_VALUES = {
    "",
    "your.email@gmail.com",
    "your-app-password",
    "replace-me",
    "changeme",
}


def env_bool(name, default=False):
    raw_value = os.environ.get(name)
    if raw_value is None:
        return default
    return raw_value.strip().lower() in {"1", "true", "yes", "on"}


def normalize_database_url(database_url):
    if not database_url:
        return f"sqlite:///{INSTANCE_DIR / 'app.db'}"
    if database_url.startswith("postgres://"):
        return database_url.replace("postgres://", "postgresql://", 1)
    return database_url


def has_real_gemini_key(api_key):
    normalized = (api_key or "").strip()
    if not normalized:
        return False
    return normalized.lower() not in INVALID_GEMINI_KEY_VALUES


def has_real_secret_key(secret_key):
    normalized = (secret_key or "").strip()
    if not normalized:
        return False
    return normalized.lower() not in INVALID_SECRET_KEY_VALUES


def has_real_mail_value(value):
    normalized = (value or "").strip()
    if not normalized:
        return False
    return normalized.lower() not in INVALID_MAIL_VALUES


class BaseConfig:
    SECRET_KEY = os.environ.get("FLASK_SECRET_KEY") or "dev-only-secret-key"
    SQLALCHEMY_DATABASE_URI = normalize_database_url(os.environ.get("DATABASE_URL"))
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": 300,
    }
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = env_bool("SESSION_COOKIE_SECURE", False)
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SECURE = env_bool("REMEMBER_COOKIE_SECURE", False)
    PERMANENT_SESSION_LIFETIME = datetime.timedelta(hours=12)
    MAX_CONTENT_LENGTH = 2 * 1024 * 1024
    ENABLE_DEV_ROUTES = env_bool("ENABLE_DEV_ROUTES", False)
    AI_CACHE_LIMIT = int(os.environ.get("AI_CACHE_LIMIT", 128))
    AI_ENABLED = has_real_gemini_key(os.environ.get("GEMINI_API_KEY"))
    JSON_SORT_KEYS = False
    MAIL_SERVER = os.environ.get("MAIL_SERVER", "smtp.gmail.com")
    MAIL_PORT = int(os.environ.get("MAIL_PORT", 587))
    MAIL_USE_TLS = env_bool("MAIL_USE_TLS", True)
    MAIL_USERNAME = os.environ.get("MAIL_USERNAME", "")
    MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD", "")
    MAIL_DEFAULT_SENDER = os.environ.get("MAIL_DEFAULT_SENDER", "")
    WKHTMLTOPDF_PATH = os.environ.get("WKHTMLTOPDF_PATH", "")
    APP_NAME = "CareCompass AI"
    BRAND_TAGLINE = "Smart medical support and care planning"
    DEBUG = env_bool("FLASK_DEBUG", False)
    TESTING = False
    PREFERRED_URL_SCHEME = "http"


class DevelopmentConfig(BaseConfig):
    DEBUG = env_bool("FLASK_DEBUG", True)


class TestingConfig(BaseConfig):
    TESTING = True
    WTF_CSRF_ENABLED = False


class ProductionConfig(BaseConfig):
    SESSION_COOKIE_SECURE = env_bool("SESSION_COOKIE_SECURE", True)
    REMEMBER_COOKIE_SECURE = env_bool("REMEMBER_COOKIE_SECURE", True)
    PREFERRED_URL_SCHEME = "https"


def get_config():
    environment = os.environ.get("FLASK_ENV", "").lower()
    if env_bool("APP_ENV_PRODUCTION", False) or environment == "production":
        if not has_real_secret_key(os.environ.get("FLASK_SECRET_KEY")):
            raise RuntimeError("A strong FLASK_SECRET_KEY must be set in production.")
        return ProductionConfig
    if environment == "testing":
        return TestingConfig
    return DevelopmentConfig
