from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user
from flask_mail import Message
from sqlalchemy import func, or_

from app.extensions import db, mail
from app.models import User


auth_bp = Blueprint("auth", __name__)


def normalize_email(email):
    return (email or "").strip().lower()


def normalize_name(name):
    normalized = " ".join((name or "").strip().split())
    return normalized


def validate_name(name):
    name = normalize_name(name)
    if len(name) < 2:
        return "Name must be at least 2 characters long."
    if len(name) > 40:
        return "Name must be under 40 characters."
    allowed = all(character.isalnum() or character in {" ", "_", "-", "."} for character in name)
    if not allowed:
        return "Name can only use letters, numbers, spaces, periods, underscores, and hyphens."
    return None


def validate_password_strength(password):
    password = password or ""
    if len(password) < 8:
        return "Password must be at least 8 characters long."
    if not any(character.isalpha() for character in password) or not any(character.isdigit() for character in password):
        return "Password must include at least one letter and one number."
    return None


def allow_local_verification():
    host = ((request.host or "").split(":", 1)[0]).lower()
    return bool(
        current_app.config.get("TESTING")
        or current_app.config.get("DEBUG")
        or current_app.config.get("ENABLE_DEV_ROUTES")
        or not current_app.config.get("SESSION_COOKIE_SECURE")
        or host in {"127.0.0.1", "localhost"}
    )


def reset_token_serializer():
    return URLSafeTimedSerializer(current_app.secret_key)


def verification_token_serializer():
    return URLSafeTimedSerializer(current_app.secret_key)


def build_reset_url(user_email):
    token = reset_token_serializer().dumps(user_email, salt="password-reset")
    return url_for("auth.reset_password", token=token, _external=True)


def build_verification_url(user_email):
    token = verification_token_serializer().dumps(user_email, salt="email-verification")
    return url_for("auth.verify_email", token=token, _external=True)


def send_password_reset_email(user_email):
    reset_url = build_reset_url(user_email)
    if not current_app.config.get("MAIL_USERNAME") or not current_app.config.get("MAIL_DEFAULT_SENDER"):
        current_app.logger.warning("Mail is not configured. Password reset email was not sent.")
        return False, reset_url

    html = render_template("auth/reset_email.html", reset_url=reset_url)
    message = Message(
        subject="Reset your CareCompass AI password",
        recipients=[user_email],
        html=html
    )
    try:
        mail.send(message)
        return True, reset_url
    except Exception as exc:
        current_app.logger.error("Failed to send password reset email: %s", exc)
        return False, reset_url


def send_verification_email(user_email):
    verification_url = build_verification_url(user_email)
    if not current_app.config.get("MAIL_USERNAME") or not current_app.config.get("MAIL_DEFAULT_SENDER"):
        current_app.logger.warning("Mail is not configured. Verification email was not sent.")
        return False, verification_url

    html = render_template("auth/verification_email.html", verification_url=verification_url)
    message = Message(
        subject="Verify your CareCompass AI account",
        recipients=[user_email],
        html=html
    )
    try:
        mail.send(message)
        return True, verification_url
    except Exception as exc:
        current_app.logger.error("Failed to send verification email: %s", exc)
        return False, verification_url


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    if request.method == "POST":
        identifier = (request.form.get("identifier") or "").strip()
        password = request.form.get("password", "")
        normalized_email = normalize_email(identifier)
        normalized_name = normalize_name(identifier)
        user = User.query.filter(
            or_(
                User.email == normalized_email,
                func.lower(User.username) == normalized_name.casefold(),
            )
        ).first()

        if not user:
            flash("We could not find that account. Create a new account to continue.", "warning")
            return redirect(url_for("auth.register"))

        if not user.email_verified:
            email_sent, verification_link = send_verification_email(user.email)
            return render_template(
                "auth/verify_email_sent.html",
                email=user.email,
                name=user.display_name,
                email_sent=email_sent,
                verification_link=verification_link if (not email_sent and allow_local_verification()) else None,
                resent=True
            )

        if not user.check_password(password):
            flash("That password is incorrect. Please try again.", "danger")
            return redirect(url_for("auth.login"))

        login_user(user, remember=True)
        flash("Welcome back. Your dashboard is ready.", "success")
        return redirect(url_for("main.dashboard"))

    return render_template("auth/login.html")


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    if request.method == "POST":
        username = normalize_name(request.form.get("username"))
        email = normalize_email(request.form.get("email"))
        password = request.form.get("password", "")

        username_error = validate_name(username)
        if username_error:
            flash(username_error, "warning")
            return redirect(url_for("auth.register"))

        password_error = validate_password_strength(password)
        if password_error:
            flash(password_error, "warning")
            return redirect(url_for("auth.register"))

        if User.query.filter(func.lower(User.username) == username.casefold()).first():
            flash("This name is already in use. Please choose another one.", "warning")
            return redirect(url_for("auth.register"))

        if User.query.filter_by(email=email).first():
            flash("An account with this email already exists. Please log in instead.", "warning")
            return redirect(url_for("auth.login"))

        user = User(username=username, email=email, email_verified=False)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        email_sent, verification_link = send_verification_email(user.email)
        return render_template(
            "auth/verify_email_sent.html",
            email=user.email,
            name=user.display_name,
            email_sent=email_sent,
            verification_link=verification_link if (not email_sent and allow_local_verification()) else None,
            resent=False
        )

    return render_template("auth/register.html")


@auth_bp.route("/verify-email/<token>")
def verify_email(token):
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    try:
        email = verification_token_serializer().loads(token, salt="email-verification", max_age=86400)
    except SignatureExpired:
        flash("This verification link has expired. Please request a new one.", "warning")
        return redirect(url_for("auth.login"))
    except BadSignature:
        flash("This verification link is invalid.", "danger")
        return redirect(url_for("auth.login"))

    user = User.query.filter_by(email=email).first_or_404()
    if not user.email_verified:
        user.email_verified = True
        db.session.commit()

    login_user(user, remember=True)
    flash("Your email has been verified successfully.", "success")
    return redirect(url_for("main.dashboard"))


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been signed out.", "info")
    return redirect(url_for("auth.login"))


@auth_bp.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    if request.method == "POST":
        email = normalize_email(request.form.get("email"))
        user = User.query.filter_by(email=email).first()

        if user:
            email_sent, reset_url = send_password_reset_email(user.email)
            if email_sent:
                flash("Password reset instructions have been sent to your email.", "success")
            elif current_app.config["ENABLE_DEV_ROUTES"]:
                flash(f"Mail is not configured. Use this local reset link: {reset_url}", "warning")
            else:
                flash("Mail is not configured for this environment, so reset email could not be sent.", "warning")
        else:
            flash("If this email exists, reset instructions have been prepared.", "info")

        return redirect(url_for("auth.login"))

    return render_template("auth/forgot_password.html")


@auth_bp.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    try:
        email = reset_token_serializer().loads(token, salt="password-reset", max_age=3600)
    except SignatureExpired:
        flash("This reset link has expired. Request a new one.", "warning")
        return redirect(url_for("auth.forgot_password"))
    except BadSignature:
        flash("This reset link is invalid.", "danger")
        return redirect(url_for("auth.forgot_password"))

    user = User.query.filter_by(email=email).first_or_404()

    if request.method == "POST":
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        if password != confirm_password:
            flash("Passwords do not match.", "danger")
            return redirect(url_for("auth.reset_password", token=token))

        password_error = validate_password_strength(password)
        if password_error:
            flash(password_error, "warning")
            return redirect(url_for("auth.reset_password", token=token))

        user.set_password(password)
        db.session.commit()

        flash("Password updated successfully. You can log in now.", "success")
        return redirect(url_for("auth.login"))

    return render_template("auth/reset_password.html", token=token, email=email)
