import json
import datetime

from flask import Blueprint, current_app, flash, jsonify, redirect, render_template, request, send_file, session, url_for
from flask_login import current_user, login_required
from sqlalchemy import func

from app.extensions import db
from app.models import Appointment, Consultation
from app.services.ai import (
    ask_gemini,
    generate_followup_questions,
    match_disease,
    normalize_analysis_payload,
    parse_ai_analysis,
    validate_symptoms,
)
from app.services.hospital import build_hospital_map
from app.services.pdf import render_consultation_pdf_bytes


main_bp = Blueprint("main", __name__)


def build_analysis_prompt(patient_name, symptoms, followup_responses=None):
    prompt = [
        f"Patient: {patient_name}.",
        f"Symptoms: {symptoms}.",
    ]
    if followup_responses:
        prompt.append(f"Follow-up responses: {followup_responses}.")
    prompt.append(
        "Provide a detailed medical analysis in valid JSON format with no comments. "
        "Include the keys: presenting_complaint, differential_diagnoses, investigations, "
        "treatment, medications, precautions, and disclaimer."
    )
    return " ".join(prompt)


def save_consultation(user_id, symptoms, followup_responses, analysis):
    consultation = Consultation(
        user_id=user_id,
        symptoms=symptoms,
        followup_responses=json.dumps(followup_responses) if followup_responses else None,
        diagnosis=json.dumps(normalize_analysis_payload(analysis))
    )
    db.session.add(consultation)
    db.session.commit()
    return consultation


def consultation_card_context(limit=4):
    consultations = (
        Consultation.query
        .filter_by(user_id=current_user.id)
        .order_by(Consultation.timestamp.desc())
        .limit(limit)
        .all()
    )
    items = []
    for consultation in consultations:
        analysis = normalize_analysis_payload(json.loads(consultation.diagnosis))
        items.append({
            "id": consultation.id,
            "timestamp": consultation.timestamp,
            "symptoms": consultation.symptoms,
            "summary": analysis.get("differential_diagnoses")
        })
    return items


@main_bp.route("/")
def home():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))
    return render_template("landing.html")


@main_bp.route("/health")
def health():
    from app import get_system_status

    status = get_system_status()
    return jsonify(status), 200 if status["database"]["healthy"] else 503


@main_bp.route("/dashboard", methods=["GET", "POST"])
@login_required
def dashboard():
    if request.method == "POST":
        symptoms = (request.form.get("symptoms") or "").strip()
        validation_error = validate_symptoms(symptoms)
        if validation_error:
            return jsonify({"success": False, "error": validation_error}), 400

        session["symptoms"] = symptoms
        matched_disease = match_disease(symptoms)
        session["matched_disease"] = matched_disease

        if matched_disease:
            return jsonify({"redirect": url_for("main.followup")})

        try:
            analysis = parse_ai_analysis(
                ask_gemini(build_analysis_prompt(current_user.display_name, symptoms), current_app.config)
            )
            save_consultation(current_user.id, symptoms, None, analysis)
            html = render_template("consultations/result_partial.html", analysis=analysis)
            return jsonify({"success": True, "html": html})
        except Exception as exc:
            current_app.logger.error("Dashboard analysis failed: %s", exc)
            return jsonify({"success": False, "error": str(exc)}), 502

    consultation_count = Consultation.query.filter_by(user_id=current_user.id).count()
    appointment_count = Appointment.query.filter_by(user_id=current_user.id).count()
    active_days = (
        db.session.query(func.count(func.distinct(func.date(Consultation.timestamp))))
        .filter(Consultation.user_id == current_user.id)
        .scalar()
    ) or 0
    next_appointment = (
        Appointment.query
        .filter(
            Appointment.user_id == current_user.id,
            Appointment.date >= datetime.date.today()
        )
        .order_by(Appointment.date.asc(), Appointment.time.asc())
        .first()
    )
    latest_consultation = (
        Consultation.query
        .filter_by(user_id=current_user.id)
        .order_by(Consultation.timestamp.desc())
        .first()
    )
    activity_score = min(
        20
        + (consultation_count * 15)
        + (appointment_count * 12)
        + (10 if latest_consultation else 0)
        + (8 if next_appointment else 0),
        100,
    )

    workspace_highlights = [
        {
            "title": "Saved consultations",
            "value": (
                f"{consultation_count} record{'s' if consultation_count != 1 else ''} saved"
                if consultation_count else
                "Your consultation history will appear here"
            ),
            "tone": "success" if consultation_count else "neutral",
        },
        {
            "title": "Appointments",
            "value": (
                f"Next visit on {next_appointment.date.strftime('%d %b %Y')}"
                if next_appointment else
                "Add your next doctor visit anytime"
            ),
            "tone": "success" if next_appointment else "neutral",
        },
        {
            "title": "Reports",
            "value": "PDF downloads are ready for saved consultations",
            "tone": "success",
        },
    ]

    return render_template(
        "consultations/dashboard.html",
        consultation_count=consultation_count,
        appointment_count=appointment_count,
        active_days=active_days,
        recent_consultations=consultation_card_context(),
        next_appointment=next_appointment,
        latest_consultation=latest_consultation,
        workspace_highlights=workspace_highlights,
        activity_score=activity_score,
    )


@main_bp.route("/followup", methods=["GET", "POST"])
@login_required
def followup():
    symptoms = session.get("symptoms")
    matched_disease = session.get("matched_disease")

    if not symptoms:
        flash("Start from the consultation dashboard first.", "warning")
        return redirect(url_for("main.dashboard"))

    questions = generate_followup_questions(symptoms, matched_disease)

    if request.method == "POST":
        answers = []
        for index, question in enumerate(questions):
            answer = (request.form.get(f"response{index}") or "").strip()
            answers.append({"question": question, "answer": answer})

        try:
            analysis = parse_ai_analysis(
                ask_gemini(build_analysis_prompt(current_user.display_name, symptoms, answers), current_app.config)
            )
            save_consultation(current_user.id, symptoms, answers, analysis)
            return render_template("consultations/result_page.html", analysis=analysis)
        except Exception as exc:
            current_app.logger.error("Follow-up analysis failed: %s", exc)
            flash(str(exc), "danger")
            return redirect(url_for("main.followup"))

    return render_template(
        "consultations/followup.html",
        disease_name=matched_disease or "your symptoms",
        questions=questions
    )


@main_bp.route("/history")
@login_required
def history():
    consultations = (
        Consultation.query
        .filter_by(user_id=current_user.id)
        .order_by(Consultation.timestamp.desc())
        .all()
    )

    date_totals = {}
    history_items = []
    for consultation in consultations:
        analysis = normalize_analysis_payload(json.loads(consultation.diagnosis))
        day = consultation.timestamp.strftime("%Y-%m-%d")
        date_totals[day] = date_totals.get(day, 0) + 1
        history_items.append({
            "id": consultation.id,
            "timestamp": consultation.timestamp,
            "symptoms": consultation.symptoms,
            "analysis": analysis
        })

    chart_labels = sorted(date_totals.keys())
    chart_data = [date_totals[label] for label in chart_labels]
    total_consultations = len(history_items)
    most_recent = history_items[0]["timestamp"] if history_items else None
    most_active_day = max(date_totals, key=date_totals.get) if date_totals else None

    return render_template(
        "consultations/history.html",
        consultations=history_items,
        chart_labels=chart_labels,
        chart_data=chart_data,
        total_consultations=total_consultations,
        most_recent=most_recent,
        most_active_day=most_active_day,
    )


@main_bp.route("/delete_consultation/<int:consultation_id>", methods=["POST"])
@login_required
def delete_consultation(consultation_id):
    consultation = Consultation.query.filter_by(id=consultation_id, user_id=current_user.id).first_or_404()
    db.session.delete(consultation)
    db.session.commit()
    flash("Consultation record deleted successfully.", "success")
    return redirect(url_for("main.history"))


@main_bp.route("/download_pdf/<int:consultation_id>")
@login_required
def download_pdf(consultation_id):
    consultation = Consultation.query.filter_by(id=consultation_id, user_id=current_user.id).first_or_404()
    try:
        pdf_buffer = render_consultation_pdf_bytes(consultation, current_user.display_name)
        return send_file(
            pdf_buffer,
            mimetype="application/pdf",
            as_attachment=True,
            download_name=f"consultation_report_{consultation.timestamp.strftime('%Y%m%d')}.pdf"
        )
    except Exception as exc:
        flash(str(exc), "warning")
        return redirect(url_for("main.history"))


@main_bp.route("/hospital_locator")
@main_bp.route("/hospital-locator")
@login_required
def hospital_locator():
    city = (request.args.get("city") or "").strip()
    map_html = None
    hospital_cards = []

    if city:
        if len(city) > 100:
            flash("City name is too long.", "warning")
            return redirect(url_for("main.hospital_locator"))
        try:
            locator_result = build_hospital_map(city)
            if not locator_result:
                flash("City not found. Try a different location.", "warning")
                return redirect(url_for("main.hospital_locator"))
            map_html = locator_result["map_html"]
            hospital_cards = locator_result["hospitals"]
        except Exception as exc:
            current_app.logger.error("Hospital locator failed: %s", exc)
            flash("We could not load the hospital map right now.", "danger")
            return redirect(url_for("main.dashboard"))

    return render_template(
        "hospital/index.html",
        city=city,
        map_html=map_html,
        hospital_cards=hospital_cards,
    )


@main_bp.route("/appointment", methods=["GET", "POST"])
@login_required
def appointment():
    appointments = (
        Appointment.query
        .filter_by(user_id=current_user.id)
        .order_by(Appointment.date.asc(), Appointment.time.asc())
        .all()
    )

    if request.method == "POST":
        date_str = request.form.get("date")
        time = (request.form.get("time") or "").strip()
        doctor = (request.form.get("doctor") or "").strip()
        notes = (request.form.get("notes") or "").strip()

        if not doctor or len(doctor) > 100:
            flash("Enter a valid doctor name under 100 characters.", "warning")
            return redirect(url_for("main.appointment"))

        try:
            date_obj = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            flash("Use the date format YYYY-MM-DD.", "danger")
            return redirect(url_for("main.appointment"))

        if date_obj < datetime.date.today():
            flash("Appointment date cannot be in the past.", "warning")
            return redirect(url_for("main.appointment"))

        new_appointment = Appointment(
            date=date_obj,
            time=time,
            doctor=doctor,
            notes=notes,
            user_id=current_user.id
        )
        db.session.add(new_appointment)
        db.session.commit()
        flash("Appointment scheduled successfully.", "success")
        return redirect(url_for("main.appointment"))

    upcoming_count = len([appointment for appointment in appointments if appointment.date >= datetime.date.today()])
    next_appointment = next(
        (appointment for appointment in appointments if appointment.date >= datetime.date.today()),
        None,
    )
    return render_template(
        "appointments/index.html",
        appointments=appointments,
        today_iso=datetime.date.today().isoformat(),
        upcoming_count=upcoming_count,
        next_appointment=next_appointment,
    )


@main_bp.route("/delete_appointment/<int:appointment_id>", methods=["POST"])
@login_required
def delete_appointment(appointment_id):
    appointment = Appointment.query.filter_by(id=appointment_id, user_id=current_user.id).first_or_404()
    db.session.delete(appointment)
    db.session.commit()
    flash("Appointment cancelled successfully.", "success")
    return redirect(url_for("main.appointment"))
