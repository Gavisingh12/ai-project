from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
load_dotenv(ROOT_DIR / ".env")

from app.config import env_bool, has_real_gemini_key, has_real_mail_value, has_real_secret_key, normalize_database_url


def is_production_target() -> bool:
    return (
        "--production" in sys.argv
        or env_bool("APP_ENV_PRODUCTION", False)
        or os.environ.get("FLASK_ENV", "").strip().lower() == "production"
    )


def print_section(title: str) -> None:
    print(f"\n{title}")
    print("-" * len(title))


def main() -> int:
    production = is_production_target()
    issues: list[str] = []
    warnings: list[str] = []

    database_url = normalize_database_url(os.environ.get("DATABASE_URL", ""))
    mail_username = os.environ.get("MAIL_USERNAME", "").strip()
    mail_password = os.environ.get("MAIL_PASSWORD", "").strip()
    mail_default_sender = os.environ.get("MAIL_DEFAULT_SENDER", "").strip()
    secret_key = os.environ.get("FLASK_SECRET_KEY", "")

    print_section("CareCompass AI Deployment Preflight")
    print(f"Mode: {'production' if production else 'development'}")
    print(f"Env file: {ROOT_DIR / '.env'}")

    if production:
        if not has_real_secret_key(secret_key):
            issues.append("FLASK_SECRET_KEY is missing or still using a placeholder value.")
        if not database_url or database_url.startswith("sqlite"):
            issues.append("DATABASE_URL must point to PostgreSQL for a live deployment.")
        if not env_bool("SESSION_COOKIE_SECURE", True):
            issues.append("SESSION_COOKIE_SECURE must be true in production.")
        if not env_bool("REMEMBER_COOKIE_SECURE", True):
            issues.append("REMEMBER_COOKIE_SECURE must be true in production.")
        if env_bool("ENABLE_DEV_ROUTES", False):
            issues.append("ENABLE_DEV_ROUTES must stay false in production.")
        if not has_real_mail_value(mail_username):
            issues.append("MAIL_USERNAME is required for live email verification.")
        if not has_real_mail_value(mail_password):
            issues.append("MAIL_PASSWORD is required for live email verification.")
        if not has_real_mail_value(mail_default_sender):
            issues.append("MAIL_DEFAULT_SENDER is required for live email verification.")
    else:
        warnings.append("Production-only checks are skipped. Run with --production before going live.")

    if mail_default_sender and "@" not in mail_default_sender:
        warnings.append("MAIL_DEFAULT_SENDER does not look like a valid email address.")
    if mail_username and "gmail.com" in mail_username.lower() and len(mail_password.replace(" ", "")) < 16:
        warnings.append("If you are using Gmail, MAIL_PASSWORD should usually be a Google App Password.")
    if not has_real_gemini_key(os.environ.get("GEMINI_API_KEY", "")):
        warnings.append("GEMINI_API_KEY is missing, so the app will use limited local fallback analysis.")

    print_section("Results")
    if issues:
        for issue in issues:
            print(f"FAIL: {issue}")
    else:
        print("PASS: No blocking deployment issues were detected.")

    if warnings:
        for warning in warnings:
            print(f"WARN: {warning}")

    print_section("Render Secrets To Set")
    secret_validators = {
        "GEMINI_API_KEY": has_real_gemini_key,
        "MAIL_USERNAME": has_real_mail_value,
        "MAIL_PASSWORD": has_real_mail_value,
        "MAIL_DEFAULT_SENDER": has_real_mail_value,
    }
    for key, validator in secret_validators.items():
        value = os.environ.get(key, "").strip()
        status = "configured" if validator(value) else "missing or placeholder"
        print(f"{key}: {status}")

    if issues:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
