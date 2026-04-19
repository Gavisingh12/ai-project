import datetime
import logging
import secrets

from dotenv import load_dotenv
from flask import Flask, abort, jsonify, render_template, request, session
from flask_login import current_user
from sqlalchemy import inspect, text
from werkzeug.middleware.proxy_fix import ProxyFix

from app.config import get_config, has_real_mail_value
from app.extensions import db, login_manager, mail
from app.models import User
from app.services.ai import configure_ai


load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s"
)


def create_app():
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(get_config())
    validate_runtime_settings(app)
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)

    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    mail.init_app(app)

    configure_ai()

    from app.services.pdf import build_pdfkit_config

    with app.app_context():
        app.extensions["pdfkit_config"] = build_pdfkit_config()
        db.create_all()
        repair_legacy_schema(app)

    register_security(app)
    register_template_helpers(app)
    register_error_handlers(app)
    register_blueprints(app)

    return app


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


def get_csrf_token():
    token = session.get("_csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["_csrf_token"] = token
    return token


def validate_csrf_token(token):
    expected = session.get("_csrf_token")
    return bool(expected and token and secrets.compare_digest(expected, token))


def build_default_username(email, used_usernames=None):
    if used_usernames is None:
        used_usernames = set()
    base_name = (email.split("@", 1)[0] if email else "member").strip()
    base_name = "".join(character for character in base_name if character.isalnum() or character in {"_", "-", " "}).strip()
    base_name = " ".join(base_name.split()) or "Member"

    candidate = base_name
    suffix = 2
    lowered = candidate.casefold()
    while lowered in used_usernames:
        candidate = f"{base_name} {suffix}"
        lowered = candidate.casefold()
        suffix += 1
    used_usernames.add(lowered)
    return candidate


def is_production_mode(app):
    return bool(app.config.get("SESSION_COOKIE_SECURE") and app.config.get("PREFERRED_URL_SCHEME") == "https")


def validate_runtime_settings(app):
    if not is_production_mode(app):
        return

    issues = []
    database_uri = app.config.get("SQLALCHEMY_DATABASE_URI", "")

    if not database_uri or database_uri.startswith("sqlite"):
        issues.append("DATABASE_URL must point to PostgreSQL in production.")
    if not app.config.get("SESSION_COOKIE_SECURE"):
        issues.append("SESSION_COOKIE_SECURE must be true in production.")
    if not app.config.get("REMEMBER_COOKIE_SECURE"):
        issues.append("REMEMBER_COOKIE_SECURE must be true in production.")
    if app.config.get("ENABLE_DEV_ROUTES"):
        issues.append("ENABLE_DEV_ROUTES must be false in production.")
    if app.config.get("REQUIRE_EMAIL_VERIFICATION"):
        invalid_mail = [
            key for key in ("MAIL_USERNAME", "MAIL_PASSWORD", "MAIL_DEFAULT_SENDER")
            if not has_real_mail_value(app.config.get(key))
        ]
    else:
        invalid_mail = []
    if invalid_mail:
        issues.append(
            "Mail settings are required for email verification in production and cannot use placeholder values: "
            + ", ".join(invalid_mail)
        )

    if issues:
        raise RuntimeError("Production configuration error:\n- " + "\n- ".join(issues))


def database_is_healthy():
    try:
        db.session.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


def repair_legacy_schema(app):
    inspector = inspect(db.engine)
    table_names = set(inspector.get_table_names())
    statements = []

    if "user" in table_names:
        user_columns = {column["name"] for column in inspector.get_columns("user")}
        if "username" not in user_columns:
            statements.append(text('ALTER TABLE "user" ADD COLUMN username VARCHAR(80)'))
        if "email_verified" not in user_columns:
            statements.append(text('ALTER TABLE "user" ADD COLUMN email_verified BOOLEAN'))
            statements.append(text('UPDATE "user" SET email_verified = 1 WHERE email_verified IS NULL'))
        if "created_at" not in user_columns:
            statements.append(text('ALTER TABLE "user" ADD COLUMN created_at DATETIME'))
            statements.append(text('UPDATE "user" SET created_at = CURRENT_TIMESTAMP WHERE created_at IS NULL'))

    if "consultation" in table_names:
        consultation_columns = {column["name"] for column in inspector.get_columns("consultation")}
        if "followup_responses" not in consultation_columns:
            statements.append(text('ALTER TABLE consultation ADD COLUMN followup_responses TEXT'))

    if "appointment" in table_names:
        appointment_columns = {column["name"] for column in inspector.get_columns("appointment")}
        if "created_at" not in appointment_columns:
            statements.append(text('ALTER TABLE appointment ADD COLUMN created_at DATETIME'))
            statements.append(text('UPDATE appointment SET created_at = CURRENT_TIMESTAMP WHERE created_at IS NULL'))

    if not statements:
        schema_changed = False
    else:
        with db.engine.begin() as connection:
            for statement in statements:
                connection.execute(statement)
        db.session.remove()
        schema_changed = True

    if "user" in table_names:
        used_usernames = set()
        users = User.query.order_by(User.id.asc()).all()
        username_updated = False
        for user in users:
            current_name = (user.username or "").strip()
            if current_name:
                used_usernames.add(current_name.casefold())
                continue
            user.username = build_default_username(user.email, used_usernames)
            username_updated = True
        if username_updated:
            db.session.commit()
            schema_changed = True

    if schema_changed:
        app.logger.info("Legacy database schema was upgraded in place.")


def get_system_status():
    database_healthy = database_is_healthy()
    return {
        "status": "ok" if database_healthy else "degraded",
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "database": {
            "healthy": database_healthy,
            "engine": current_app_config("SQLALCHEMY_DATABASE_URI").split("://", 1)[0]
        },
        "ai": {
            "enabled": current_app_config("AI_ENABLED"),
            "provider": "gemini"
        },
        "pdf_export": {
            "enabled": True,
            "mode": "wkhtmltopdf" if current_app_extension("pdfkit_config") else "built-in"
        }
    }


def current_app_config(name):
    from flask import current_app

    return current_app.config[name]


def current_app_extension(name):
    from flask import current_app

    return current_app.extensions.get(name)


def register_security(app):
    @app.before_request
    def protect_mutating_requests():
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            if app.config.get("TESTING"):
                return
            token = request.form.get("csrf_token") or request.headers.get("X-CSRFToken")
            if not validate_csrf_token(token):
                abort(400, description="Invalid or missing CSRF token.")


def register_template_helpers(app):
    def password_reset_available():
        return bool(
            app.config.get("ENABLE_DEV_ROUTES")
            or all(
                has_real_mail_value(app.config.get(key))
                for key in ("MAIL_USERNAME", "MAIL_PASSWORD", "MAIL_DEFAULT_SENDER")
            )
        )

    @app.context_processor
    def inject_helpers():
        return {
            "app_name": app.config["APP_NAME"],
            "brand_tagline": app.config["BRAND_TAGLINE"],
            "csrf_token": get_csrf_token,
            "system_status": get_system_status(),
            "is_authenticated": current_user.is_authenticated,
            "email_verification_required": app.config["REQUIRE_EMAIL_VERIFICATION"],
            "password_reset_available": password_reset_available(),
        }


def wants_json_response():
    return request.path.startswith("/health") or request.accept_mimetypes.best == "application/json"


def register_error_handlers(app):
    @app.errorhandler(400)
    def bad_request(error):
        if wants_json_response():
            return jsonify({"status": "error", "message": str(error)}), 400
        return render_template("errors/400.html", message=str(error)), 400

    @app.errorhandler(404)
    def not_found(error):
        if wants_json_response():
            return jsonify({"status": "error", "message": "Resource not found"}), 404
        return render_template("errors/404.html"), 404

    @app.errorhandler(500)
    def server_error(error):
        app.logger.exception("Unhandled server error: %s", error)
        if wants_json_response():
            return jsonify({"status": "error", "message": "Internal server error"}), 500
        return render_template("errors/500.html"), 500


def register_blueprints(app):
    from app.routes.auth import auth_bp
    from app.routes.main import main_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
