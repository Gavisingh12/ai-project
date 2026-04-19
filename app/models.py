import datetime
import re

from flask_login import UserMixin

from app.extensions import db


def utc_now():
    return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80))
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    email_verified = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=utc_now)
    consultations = db.relationship("Consultation", backref="user", lazy=True, cascade="all, delete-orphan")
    appointments = db.relationship("Appointment", backref="user", lazy=True, cascade="all, delete-orphan")

    @property
    def display_name(self):
        name = (self.username or "").strip()
        email_name = (self.email.split("@", 1)[0] or "").strip()

        if name and name.casefold() != email_name.casefold():
            return name

        cleaned = re.sub(r"\d+$", "", email_name)
        cleaned = re.sub(r"[._-]+", " ", cleaned)
        cleaned = " ".join(cleaned.split()).strip()
        if not cleaned:
            return "Member"
        return " ".join(part.capitalize() for part in cleaned.split())

    @property
    def greeting_name(self):
        parts = self.display_name.split()
        return parts[0] if parts else "there"

    def set_password(self, password):
        from werkzeug.security import generate_password_hash

        self.password = generate_password_hash(password)

    def check_password(self, password):
        from werkzeug.security import check_password_hash

        return check_password_hash(self.password, password)


class Consultation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    symptoms = db.Column(db.Text, nullable=False)
    followup_responses = db.Column(db.Text)
    diagnosis = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=utc_now)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)


class Appointment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False)
    time = db.Column(db.String(10), nullable=False)
    doctor = db.Column(db.String(100), nullable=False)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=utc_now)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
