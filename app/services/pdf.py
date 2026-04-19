import json
import shutil
import textwrap
from io import BytesIO

import pdfkit
from flask import current_app, render_template

from app.services.ai import analysis_points, analysis_text, normalize_analysis_payload


def build_pdfkit_config():
    wkhtmltopdf_path = current_app.config.get("WKHTMLTOPDF_PATH") or shutil.which("wkhtmltopdf")
    if not wkhtmltopdf_path:
        current_app.logger.info("wkhtmltopdf was not found. Built-in PDF export will be used.")
        return None
    try:
        return pdfkit.configuration(wkhtmltopdf=wkhtmltopdf_path)
    except Exception as exc:
        current_app.logger.warning("wkhtmltopdf configuration failed. Built-in PDF export will be used: %s", exc)
        return None


def pdf_options():
    return {
        "page-size": "A4",
        "margin-top": "0.6in",
        "margin-right": "0.6in",
        "margin-bottom": "0.6in",
        "margin-left": "0.6in",
        "encoding": "UTF-8",
        "enable-local-file-access": None
    }


def pdf_escape(text):
    safe_text = (text or "").replace("\r", "")
    safe_text = safe_text.encode("latin-1", "replace").decode("latin-1")
    return safe_text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def wrap_pdf_lines(text, width=82):
    normalized = (text or "").replace("\r", "")
    parts = normalized.splitlines() or [""]
    wrapped = []
    for part in parts:
        stripped = part.strip()
        if not stripped:
            wrapped.append("")
            continue
        wrapped.extend(textwrap.wrap(stripped, width=width) or [""])
    return wrapped


def consultation_report_lines(consultation, patient_name, analysis):
    sections = [
        ("Date", consultation.timestamp.strftime('%d %b %Y, %I:%M %p')),
        ("Patient", patient_name),
        ("Symptoms", consultation.symptoms),
        ("Presenting Complaint", analysis["presenting_complaint"]),
        ("Differential Diagnoses", analysis["differential_diagnoses"]),
        ("Investigations", analysis["investigations"]),
        ("Treatment", analysis["treatment"]),
        ("Medications", analysis["medications"]),
        ("Precautions", analysis["precautions"]),
        ("Disclaimer", analysis["disclaimer"]),
    ]

    lines = []
    for heading, content in sections:
        lines.append(f"{heading}:")
        if heading in {"Differential Diagnoses", "Investigations", "Treatment", "Medications", "Precautions"}:
            for item in analysis_points(content):
                lines.extend(wrap_pdf_lines(f"- {item}"))
        else:
            lines.extend(wrap_pdf_lines(analysis_text(content)))
        lines.append("")
    return lines


def build_pdf_page_stream(title, lines):
    commands = [
        "BT",
        "/F1 18 Tf",
        "50 760 Td",
        f"({pdf_escape(title)}) Tj",
        "0 -30 Td",
        "/F1 11 Tf",
        "15 TL",
    ]
    for line in lines:
        commands.append(f"({pdf_escape(line)}) Tj")
        commands.append("T*")
    commands.append("ET")
    return "\n".join(commands).encode("latin-1", "replace")


def build_builtin_pdf(lines, title="CareCompass AI Consultation Report"):
    page_chunks = []
    max_lines_per_page = 42
    for index in range(0, len(lines), max_lines_per_page):
        page_chunks.append(lines[index:index + max_lines_per_page])
    if not page_chunks:
        page_chunks = [[]]

    font_id = 3 + (len(page_chunks) * 2)
    objects = {
        1: b"<< /Type /Catalog /Pages 2 0 R >>",
        font_id: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    }

    page_refs = []
    for page_index, chunk in enumerate(page_chunks):
        page_id = 3 + (page_index * 2)
        content_id = page_id + 1
        page_title = title if page_index == 0 else f"{title} (continued)"
        stream = build_pdf_page_stream(page_title, chunk)
        objects[content_id] = b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n" + stream + b"\nendstream"
        objects[page_id] = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Resources << /Font << /F1 {font_id} 0 R >> >> /Contents {content_id} 0 R >>"
        ).encode("latin-1")
        page_refs.append(f"{page_id} 0 R")

    objects[2] = f"<< /Type /Pages /Kids [{' '.join(page_refs)}] /Count {len(page_refs)} >>".encode("latin-1")

    pdf_bytes = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"
    offsets = [0]

    for object_id in range(1, font_id + 1):
        offsets.append(len(pdf_bytes))
        pdf_bytes += f"{object_id} 0 obj\n".encode("ascii")
        pdf_bytes += objects[object_id]
        pdf_bytes += b"\nendobj\n"

    xref_offset = len(pdf_bytes)
    pdf_bytes += f"xref\n0 {font_id + 1}\n".encode("ascii")
    pdf_bytes += b"0000000000 65535 f \n"
    for object_id in range(1, font_id + 1):
        pdf_bytes += f"{offsets[object_id]:010d} 00000 n \n".encode("ascii")

    pdf_bytes += (
        f"trailer\n<< /Size {font_id + 1} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF"
    ).encode("ascii")
    return BytesIO(pdf_bytes)


def render_consultation_pdf_bytes(consultation, patient_name):
    pdf_config = current_app.extensions.get("pdfkit_config")
    analysis = normalize_analysis_payload(json.loads(consultation.diagnosis))

    if not pdf_config:
        return build_builtin_pdf(
            consultation_report_lines(consultation, patient_name, analysis)
        )

    html_content = render_template(
        "consultations/report_pdf.html",
        consultation=consultation,
        patient_name=patient_name,
        analysis=analysis
    )
    return BytesIO(
        pdfkit.from_string(
            html_content,
            False,
            configuration=pdf_config,
            options=pdf_options()
        )
    )
