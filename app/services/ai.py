import json
import logging
import os
import re
from collections import OrderedDict

import google.generativeai as genai
from rapidfuzz import fuzz, process


ai_cache = OrderedDict()
logger = logging.getLogger(__name__)

ANALYSIS_DEFAULTS = {
    "presenting_complaint": "No presenting complaint was generated.",
    "differential_diagnoses": "No differential diagnoses were generated.",
    "investigations": "No investigations were generated.",
    "treatment": "No treatment guidance was generated.",
    "medications": "No medication guidance was generated.",
    "precautions": "No precautions were generated.",
    "disclaimer": "This is an AI-generated analysis and should not replace professional medical advice."
}
ANALYSIS_LIST_KEYS = {
    "differential_diagnoses",
    "investigations",
    "treatment",
    "medications",
    "precautions",
}

DISEASE_QUESTIONS = {
    "fever": [
        "How high is your fever right now?",
        "Are you also having chills or strong body aches?",
        "Did the fever start suddenly or build up slowly?",
        "Do you have a cough, sore throat, or runny nose?",
        "Have you travelled recently or been around anyone sick?"
    ],
    "diabetes": [
        "Have you been feeling unusually thirsty?",
        "Are you urinating more often than usual?",
        "Have you noticed any unexplained weight changes?",
        "Do you often feel tired or low on energy?",
        "Do you have a family history of diabetes?"
    ],
    "migraine": [
        "Is the headache one-sided or all over the head?",
        "Are you sensitive to light or sound?",
        "Do you feel nauseated during the headache?",
        "How long does the headache usually last?"
    ],
    "depression": [
        "How long have you been feeling low or emotionally drained?",
        "Have you lost interest in things you usually enjoy?",
        "Has your sleep changed recently?",
        "Are you finding it difficult to focus or make decisions?"
    ],
    "heart disease": [
        "Are you feeling chest pain, pressure, or tightness?",
        "Do you get short of breath during normal activity?",
        "Do you have a history of high blood pressure?",
        "Is there a family history of heart disease?"
    ],
    "covid-19": [
        "Have you noticed fever, cough, or body aches?",
        "Have you lost taste or smell recently?",
        "Have you been in contact with anyone unwell?",
        "Are your symptoms improving, stable, or worsening?"
    ],
    "asthma": [
        "Do you wheeze or feel tightness in your chest?",
        "Do symptoms get worse with exercise or dust exposure?",
        "Are symptoms worse at night?",
        "Do you have an inhaler and has it helped?"
    ],
    "gastritis": [
        "Are you feeling burning pain or heaviness in the upper abdomen?",
        "Do symptoms get worse after eating spicy or oily food?",
        "Are you feeling bloated or nauseated?",
        "Have you taken painkillers regularly in the last few days?"
    ]
}

DEFAULT_FOLLOWUP_QUESTIONS = [
    "How severe is this problem on a scale from 1 to 10?",
    "How long have you been dealing with these symptoms?",
    "Have you taken any medicine or home treatment yet?",
    "What symptom is worrying you the most right now?"
]


def configure_ai():
    api_key = os.environ.get("GEMINI_API_KEY")
    if api_key and api_key.strip().lower() not in {
        "",
        "your-gemini-api-key-here",
        "replace-with-your-gemini-key",
        "replace-me",
        "changeme",
        "demo-key",
    }:
        genai.configure(api_key=api_key)


def normalize_analysis_payload(payload):
    return {
        key: payload.get(key) or default
        for key, default in ANALYSIS_DEFAULTS.items()
    }


def analysis_text(value):
    if isinstance(value, list):
        return ", ".join(filter(None, [analysis_text(item) for item in value]))
    if isinstance(value, dict):
        parts = [f"{key}: {analysis_text(item)}" for key, item in value.items() if item]
        return "; ".join(parts)
    text = str(value or "").replace("\r", "\n").replace("\\n", "\n").strip()
    text = text.strip("[]")
    text = re.sub(r"^[\"']+|[\"']+$", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def analysis_points(value, max_items=6):
    if isinstance(value, list):
        raw_chunks = [analysis_text(item) for item in value]
    elif isinstance(value, dict):
        raw_chunks = [f"{key}: {analysis_text(item)}" for key, item in value.items() if item]
    else:
        normalized = str(value or "").replace("\r", "\n").replace("\\n", "\n").strip()
        normalized = normalized.strip("[]")
        normalized = normalized.replace('", "', '"\n"').replace("', '", "'\n'")
        raw_chunks = re.split(r"\n+|;\s+|\s\|\s", normalized)

    points = []
    for chunk in raw_chunks:
        piece = analysis_text(chunk)
        piece = re.sub(r"^[\-\u2022\*\d\.\)\(]+\s*", "", piece)
        piece = piece.strip(" \"'")
        if not piece:
            continue
        if len(piece) > 180 and len(raw_chunks) == 1:
            for sentence in re.split(r"(?<=[.!?])\s+(?=[A-Z])", piece):
                sentence = analysis_text(sentence)
                if sentence:
                    points.append(sentence)
        else:
            points.append(piece)

    deduped = []
    seen = set()
    for point in points:
        key = point.casefold()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(point)

    return deduped[:max_items] or [analysis_text(value)]


def analysis_summary(value, max_items=2):
    points = analysis_points(value, max_items=max_items)
    return " ".join(points[:max_items]).strip()


def clean_json_response(raw_json):
    cleaned = (raw_json or "").strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        cleaned = "\n".join(lines)
    cleaned = re.sub(r"//.*", "", cleaned)
    return cleaned.strip()


def parse_ai_analysis(ai_response):
    parsed_response = json.loads(clean_json_response(ai_response))
    if not isinstance(parsed_response, dict):
        raise ValueError("AI response was not a valid JSON object.")
    return normalize_analysis_payload(parsed_response)


def validate_symptoms(symptoms):
    normalized = (symptoms or "").strip()
    if len(normalized) < 10:
        return "Please describe your symptoms in a bit more detail."
    if len(normalized) > 1000:
        return "Symptoms are too long. Please keep the description under 1000 characters."
    return None


def generate_followup_questions(symptoms, matched_disease):
    if matched_disease and matched_disease in DISEASE_QUESTIONS:
        return DISEASE_QUESTIONS[matched_disease]
    return DEFAULT_FOLLOWUP_QUESTIONS


def match_disease(user_input):
    diseases = list(DISEASE_QUESTIONS.keys())
    if not diseases:
        return None
    match = process.extractOne(
        (user_input or "").strip(),
        diseases,
        scorer=fuzz.WRatio
    )
    if not match:
        return None
    best_match, score, _ = match
    return best_match if score >= 60 else None


def cache_ai_output(prompt, output, app_config):
    ai_cache[prompt] = output
    ai_cache.move_to_end(prompt)
    if len(ai_cache) > app_config["AI_CACHE_LIMIT"]:
        ai_cache.popitem(last=False)
    return output


def extract_symptom_context(prompt):
    match = re.search(
        r"Symptoms:\s*(.*?)(?:\.\s*Follow-up responses:|\.\s*Provide a detailed medical analysis|$)",
        prompt or "",
        flags=re.IGNORECASE | re.DOTALL,
    )
    if match:
        return " ".join(match.group(1).split())
    return (prompt or "").strip()


def build_local_demo_analysis(prompt):
    symptom_context = extract_symptom_context(prompt)
    lowered = symptom_context.lower()

    presenting_complaint = symptom_context or "General symptoms reported by the user."

    possible_conditions = []
    if any(keyword in lowered for keyword in ["headache", "migraine", "head ache"]):
        possible_conditions.extend(["Tension-type headache", "Migraine episode", "Dehydration or stress-related headache"])
    if any(keyword in lowered for keyword in ["fever", "cough", "sore throat", "cold", "body ache"]):
        possible_conditions.extend(["Viral upper respiratory infection", "Flu-like illness", "Inflammatory or infectious process"])
    if any(keyword in lowered for keyword in ["stomach", "abdominal", "vomit", "nausea", "gas", "acidity"]):
        possible_conditions.extend(["Gastritis or acid irritation", "Indigestion", "Mild gastrointestinal infection"])
    if any(keyword in lowered for keyword in ["chest pain", "breath", "shortness of breath", "palpitation"]):
        possible_conditions.extend(["Cardiorespiratory cause that needs prompt assessment", "Anxiety-related symptoms", "Musculoskeletal chest discomfort"])
    if any(keyword in lowered for keyword in ["fatigue", "weakness", "tired"]):
        possible_conditions.extend(["Viral syndrome", "Sleep deprivation or stress", "Nutritional or metabolic imbalance"])

    if not possible_conditions:
        possible_conditions = [
            "Viral illness",
            "Stress-related or lifestyle-triggered symptoms",
            "Condition requiring in-person clinical evaluation if symptoms persist",
        ]

    investigations = [
        "Basic vital signs review",
        "Focused physical examination",
        "Symptom-duration review",
    ]
    if "fever" in lowered:
        investigations.append("Temperature monitoring and CBC if symptoms continue")
    if any(keyword in lowered for keyword in ["headache", "migraine"]):
        investigations.append("Neurological assessment if symptoms are severe or recurrent")
    if any(keyword in lowered for keyword in ["stomach", "abdominal", "nausea", "vomit"]):
        investigations.append("Hydration review and abdominal examination")

    treatment = (
        "Use supportive care first: adequate hydration, rest, light meals if tolerated, and short-term symptom monitoring. "
        "If symptoms are worsening, persistent, or unusually severe, arrange an in-person medical review."
    )
    medications = (
        "Only consider common over-the-counter symptom relief if it is normally safe for you, such as acetaminophen/paracetamol for pain or fever. "
        "Avoid self-medicating if you have allergies, chronic conditions, pregnancy, or are unsure what is safe."
    )
    precautions = (
        "Seek urgent medical help for red flags such as chest pain, difficulty breathing, confusion, fainting, seizures, very high fever, "
        "sudden severe headache, dehydration, or worsening symptoms."
    )

    analysis = {
        "presenting_complaint": presenting_complaint,
        "differential_diagnoses": "; ".join(dict.fromkeys(possible_conditions)),
        "investigations": "; ".join(dict.fromkeys(investigations)),
        "treatment": treatment,
        "medications": medications,
        "precautions": precautions,
        "disclaimer": (
            "This response was generated in standard guidance mode. It is educational support only and not a medical diagnosis."
        ),
    }
    return json.dumps(analysis)


def ask_gemini(prompt, app_config):
    if prompt in ai_cache:
        ai_cache.move_to_end(prompt)
        return ai_cache[prompt]

    if not app_config.get("AI_ENABLED", False):
        return cache_ai_output(prompt, build_local_demo_analysis(prompt), app_config)

    try:
        model = genai.GenerativeModel("gemini-2.5-flash")
        response = model.generate_content(prompt)
        output = response.text if response.text else build_local_demo_analysis(prompt)
    except Exception as exc:
        logger.warning("Gemini request failed. Falling back to local demo analysis: %s", exc)
        output = build_local_demo_analysis(prompt)

    return cache_ai_output(prompt, output, app_config)
