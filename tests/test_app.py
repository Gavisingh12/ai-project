import os
import re
import uuid
import importlib
from pathlib import Path
from urllib.parse import urlparse

import pytest
from flask import Flask
from sqlalchemy import text


TEST_DB_PATH = Path(__file__).resolve().parent / f"test_{uuid.uuid4().hex}.db"
os.environ["FLASK_SECRET_KEY"] = "test-secret-key"
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB_PATH}"
os.environ["ENABLE_DEV_ROUTES"] = "False"
os.environ["GEMINI_API_KEY"] = ""

main2 = importlib.import_module("main2")
app_module = importlib.import_module("app")
main_routes = importlib.import_module("app.routes.main")
ai_service = importlib.import_module("app.services.ai")


def extract_csrf_token(html):
    match = re.search(r'name="csrf_token" value="([^"]+)"', html)
    assert match, "CSRF token was not found in the page."
    return match.group(1)


def extract_verification_link(html):
    match = re.search(r'href="([^"]*verify-email/[^"]+)"', html)
    if not match:
        return None
    verification_url = match.group(1)
    parsed = urlparse(verification_url)
    return parsed.path or verification_url


@pytest.fixture(autouse=True)
def reset_database():
    with main2.app.app_context():
        main2.db.drop_all()
        main2.db.create_all()
    yield
    with main2.app.app_context():
        main2.db.session.remove()
        main2.db.drop_all()


@pytest.fixture
def client():
    main2.app.config.update(TESTING=True)
    with main2.app.test_client() as client:
        yield client


def register_user(client, username="user", email="user@example.com", password="Password123"):
    response = client.get("/register")
    token = extract_csrf_token(response.get_data(as_text=True))
    register_response = client.post(
        "/register",
        data={
            "username": username,
            "email": email,
            "password": password,
            "csrf_token": token
        },
        follow_redirects=True
    )
    verify_link = extract_verification_link(register_response.get_data(as_text=True))
    if verify_link:
        verify_response = client.get(verify_link, follow_redirects=True)
    else:
        verify_response = register_response
    client.get("/logout", follow_redirects=True)
    return register_response, verify_response


def login_user(client, identifier="user@example.com", password="Password123"):
    response = client.get("/login")
    token = extract_csrf_token(response.get_data(as_text=True))
    return client.post(
        "/login",
        data={
            "identifier": identifier,
            "password": password,
            "csrf_token": token
        },
        follow_redirects=True
    )


def test_health_endpoint_reports_ok(client):
    response = client.get("/health", headers={"Accept": "application/json"})

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] == "ok"
    assert payload["database"]["healthy"] is True


def test_robots_and_sitemap_routes_exist(client):
    robots_response = client.get("/robots.txt")
    sitemap_response = client.get("/sitemap.xml")

    assert robots_response.status_code == 200
    assert b"Sitemap:" in robots_response.data
    assert sitemap_response.status_code == 200
    assert b"<urlset" in sitemap_response.data


def test_register_and_login_flow(client):
    register_response, verify_response = register_user(client)
    assert b"Account created successfully" in register_response.data
    assert b"Hello, User" in verify_response.data

    login_response = login_user(client)
    assert b"Hello, User" in login_response.data


def test_login_with_username_works(client):
    register_user(client, username="Govinder Singh", email="govinder@example.com")

    login_response = login_user(client, identifier="Govinder Singh")
    assert b"Hello, Govinder" in login_response.data


def test_dashboard_creates_consultation_with_mocked_ai(client, monkeypatch):
    register_user(client)
    login_user(client)

    monkeypatch.setattr(main_routes, "match_disease", lambda _: None)
    monkeypatch.setattr(
        main_routes,
        "ask_gemini",
        lambda prompt, app_config: """
        {
          "presenting_complaint": "Fatigue and body pain",
          "differential_diagnoses": "Viral syndrome",
          "investigations": "CBC",
          "treatment": "Rest and hydration",
          "medications": "Paracetamol if needed",
          "precautions": "Monitor fever",
          "disclaimer": "Educational output only"
        }
        """
    )

    dashboard_page = client.get("/dashboard")
    token = extract_csrf_token(dashboard_page.get_data(as_text=True))
    response = client.post(
        "/dashboard",
        data={
            "symptoms": "general fatigue with mild body pain for two days",
            "csrf_token": token
        },
        headers={"Accept": "application/json"}
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert "Fatigue and body pain" in payload["html"]

    with main2.app.app_context():
        assert main2.Consultation.query.count() == 1


def test_dashboard_falls_back_to_local_demo_analysis_when_ai_is_unavailable(client, monkeypatch):
    register_user(client, username="Demo User", email="demo@example.com")
    login_user(client, identifier="demo@example.com")

    monkeypatch.setattr(main_routes, "match_disease", lambda _: None)

    dashboard_page = client.get("/dashboard")
    token = extract_csrf_token(dashboard_page.get_data(as_text=True))
    response = client.post(
        "/dashboard",
        data={
            "symptoms": "I have had a headache and mild weakness since morning",
            "csrf_token": token
        },
        headers={"Accept": "application/json"}
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert "standard guidance mode" in payload["html"]


def test_dev_routes_are_disabled_by_default(client):
    response = client.get("/list_users")
    assert response.status_code == 404


def test_delete_consultation_uses_post_with_csrf(client):
    register_user(client)
    login_user(client)

    with main2.app.app_context():
        user = main2.User.query.filter_by(email="user@example.com").first()
        consultation = main2.Consultation(
            user_id=user.id,
            symptoms="cough and fever",
            diagnosis='{"presenting_complaint":"cough"}'
        )
        main2.db.session.add(consultation)
        main2.db.session.commit()
        consultation_id = consultation.id

    history_page = client.get("/history")
    token = extract_csrf_token(history_page.get_data(as_text=True))
    response = client.post(
        f"/delete_consultation/{consultation_id}",
        data={"csrf_token": token},
        follow_redirects=True
    )

    assert response.status_code == 200
    assert b"Consultation record deleted successfully" in response.data

    with main2.app.app_context():
        assert main2.Consultation.query.count() == 0


def test_download_pdf_works_without_wkhtmltopdf(client):
    register_user(client, username="Report User", email="report@example.com")
    login_user(client, identifier="report@example.com")

    with main2.app.app_context():
        user = main2.User.query.filter_by(email="report@example.com").first()
        consultation = main2.Consultation(
            user_id=user.id,
            symptoms="headache and fatigue",
            diagnosis='{"presenting_complaint":"headache","differential_diagnoses":"tension headache"}'
        )
        main2.db.session.add(consultation)
        main2.db.session.commit()
        consultation_id = consultation.id

    response = client.get(f"/download_pdf/{consultation_id}")

    assert response.status_code == 200
    assert response.mimetype == "application/pdf"
    assert response.data.startswith(b"%PDF-1.4")


def test_legacy_user_schema_is_repaired():
    with main2.app.app_context():
        main2.db.drop_all()
        main2.db.session.execute(text("DROP TABLE IF EXISTS user"))
        main2.db.session.execute(text("""
            CREATE TABLE user (
                id INTEGER PRIMARY KEY,
                email VARCHAR(120) NOT NULL,
                password VARCHAR(200) NOT NULL
            )
        """))
        main2.db.session.commit()

        app_module.repair_legacy_schema(main2.app)

        columns = {
            row[1]
            for row in main2.db.session.execute(text('PRAGMA table_info("user")')).fetchall()
        }

        assert "username" in columns
        assert "email_verified" in columns
        assert "created_at" in columns


def test_unverified_user_is_activated_on_login_when_verification_is_disabled(client):
    response = client.get("/register")
    token = extract_csrf_token(response.get_data(as_text=True))
    client.post(
        "/register",
        data={
            "username": "Pending User",
            "email": "pending@example.com",
            "password": "Password123",
            "csrf_token": token
        },
        follow_redirects=True
    )

    with main2.app.app_context():
        user = main2.User.query.filter_by(email="pending@example.com").first()
        user.email_verified = False
        main2.db.session.commit()

    client.get("/logout", follow_redirects=True)
    login_response = login_user(client, identifier="pending@example.com")
    assert b"Hello, Pending" in login_response.data


def test_validate_runtime_settings_blocks_unsafe_production_config():
    app = Flask(__name__)
    app.config.update(
        SQLALCHEMY_DATABASE_URI="sqlite:///local.db",
        SESSION_COOKIE_SECURE=True,
        REMEMBER_COOKIE_SECURE=True,
        PREFERRED_URL_SCHEME="https",
        ENABLE_DEV_ROUTES=False,
        REQUIRE_EMAIL_VERIFICATION=True,
        MAIL_USERNAME="",
        MAIL_PASSWORD="",
        MAIL_DEFAULT_SENDER="",
    )

    with pytest.raises(RuntimeError, match="Production configuration error"):
        app_module.validate_runtime_settings(app)


def test_validate_runtime_settings_blocks_placeholder_mail_values():
    app = Flask(__name__)
    app.config.update(
        SQLALCHEMY_DATABASE_URI="postgresql://user:pass@localhost:5432/carecompass",
        SESSION_COOKIE_SECURE=True,
        REMEMBER_COOKIE_SECURE=True,
        PREFERRED_URL_SCHEME="https",
        ENABLE_DEV_ROUTES=False,
        REQUIRE_EMAIL_VERIFICATION=True,
        MAIL_USERNAME="your.email@gmail.com",
        MAIL_PASSWORD="your-app-password",
        MAIL_DEFAULT_SENDER="your.email@gmail.com",
    )

    with pytest.raises(RuntimeError, match="placeholder values"):
        app_module.validate_runtime_settings(app)


def test_validate_runtime_settings_allows_demo_mode_without_mail():
    app = Flask(__name__)
    app.config.update(
        SQLALCHEMY_DATABASE_URI="postgresql://user:pass@localhost:5432/carecompass",
        SESSION_COOKIE_SECURE=True,
        REMEMBER_COOKIE_SECURE=True,
        PREFERRED_URL_SCHEME="https",
        ENABLE_DEV_ROUTES=False,
        REQUIRE_EMAIL_VERIFICATION=False,
        MAIL_USERNAME="",
        MAIL_PASSWORD="",
        MAIL_DEFAULT_SENDER="",
    )

    app_module.validate_runtime_settings(app)


def test_normalize_database_url_uses_psycopg_driver():
    assert main2.app.config["SQLALCHEMY_DATABASE_URI"].startswith("sqlite:///")
    assert app_module.get_config
    normalized = importlib.import_module("app.config").normalize_database_url("postgresql://user:pass@localhost:5432/carecompass")
    assert normalized == "postgresql+psycopg://user:pass@localhost:5432/carecompass"
    normalized_legacy = importlib.import_module("app.config").normalize_database_url("postgres://user:pass@localhost:5432/carecompass")
    assert normalized_legacy == "postgresql+psycopg://user:pass@localhost:5432/carecompass"


def test_analysis_points_split_messy_model_output():
    messy = '["Primary headaches\\n- Tension-type headache; Migraine episode; Dehydration or eye strain"]'
    points = ai_service.analysis_points(messy)

    assert len(points) >= 2
    assert any("Migraine" in point for point in points)
