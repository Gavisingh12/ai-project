import os
import re
import json
import datetime
from flask import Flask, render_template_string, request, redirect, url_for, flash, session, send_file, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, logout_user, login_required, current_user, UserMixin
from flask_mail import Mail, Message
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadSignature
from fuzzywuzzy import process
import google.generativeai as genai
import folium
from geopy.geocoders import Nominatim
import pdfkit

# --- App Configuration ---
app = Flask(__name__)
app.secret_key = 'AIzaSyCBmRzH8TKUveHT8l5v0QkleEK3K5dRtXs'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///app.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SERVER_NAME'] = '127.0.0.1:5000'

# --- Mail Configuration ---
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'your.email@gmail.com'
app.config['MAIL_PASSWORD'] = 'your-app-password'
app.config['MAIL_DEFAULT_SENDER'] = 'your.email@gmail.com'

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
mail = Mail(app)

# Serializer for email confirmation tokens
s = URLSafeTimedSerializer(app.secret_key)

# PDFKit configuration
PDFKIT_CONFIG = pdfkit.configuration(wkhtmltopdf=r'C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe')
PDF_OPTIONS = {
    'page-size': 'A4',
    'margin-top': '0.75in',
    'margin-right': '0.75in',
    'margin-bottom': '0.75in',
    'margin-left': '0.75in',
    'encoding': "UTF-8",
    'enable-local-file-access': None
}

# --- Configure Gemini AI ---
genai.configure(api_key="AIzaSyCBmRzH8TKUveHT8l5v0QkleEK3K5dRtXs")

# --- In-Memory Cache for AI Responses ---
ai_cache = {}

# --- Database Models ---
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    email_verified = db.Column(db.Boolean, default=True)
    consultations = db.relationship('Consultation', backref='user', lazy=True)
    appointments = db.relationship('Appointment', backref='user', lazy=True)

class Consultation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    symptoms = db.Column(db.Text, nullable=False)
    followup_responses = db.Column(db.Text)
    diagnosis = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

class Appointment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False)
    time = db.Column(db.String(10), nullable=False)
    doctor = db.Column(db.String(100), nullable=False)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

with app.app_context():
    db.create_all()

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

# --- Predefined Disease Questions ---
# Used if a static match is found.
disease_questions = {
    "fever": [
        "How high is your fever? (1) Above 102°F (2) Between 99-102°F (3) No fever (4) Not sure",
        "Do you have chills or body aches? (1) Yes, severe (2) Yes, mild (3) No (4) Not sure",
        "Are you experiencing a sore throat? (1) Yes, severe (2) Yes, mild (3) No (4) Not sure",
        "Do you have a cough? (1) Dry cough (2) Wet cough (3) No cough (4) Occasionally",
        "Have you traveled recently? (1) Yes, internationally (2) Yes, domestically (3) No (4) Not sure"
    ],
    "diabetes": [
        "Have you been experiencing excessive thirst? (1) Yes, always (2) Yes, sometimes (3) No (4) Not sure",
        "Do you urinate frequently? (1) Yes, very often (2) Yes, occasionally (3) No (4) Not sure",
        "Have you experienced unexplained weight loss? (1) Yes, significant (2) Yes, mild (3) No (4) Not sure",
        "Do you feel fatigued often? (1) Yes, constantly (2) Yes, sometimes (3) No (4) Only after activity",
        "Do you have a family history of diabetes? (1) Yes, both parents (2) Yes, one parent (3) No (4) Not sure"
    ],
    # ... add additional diseases as needed ...
    "migraine": [
        "Do you experience severe headaches?",
        "Do you have sensitivity to light or sound?",
        "Do you experience nausea during headaches?",
        "Does your headache last for more than 4 hours?"
    ],
    "depression": [
        "Do you feel persistently sad or hopeless?",
        "Have you lost interest in activities you once enjoyed?",
        "Do you experience changes in sleep patterns?",
        "Do you have trouble concentrating or making decisions?"
    ],
    "food poisoning": [
        "Have you experienced nausea or vomiting?",
        "Do you have diarrhea?",
        "Did you eat anything unusual or expired recently?",
        "Do you have stomach cramps?"
    ],
    "heart disease": [
        "Do you experience chest pain or discomfort?",
        "Do you feel shortness of breath?",
        "Do you have high blood pressure?",
        "Do you have a family history of heart disease?"
    ],
    "pneumonia": [
        "Do you have difficulty breathing?\n1) Yes, severe\n2) Yes, mild\n3) No\n4) Not sure",
        "Have you had a fever with a productive cough?\n1) Yes\n2) No\n3) Sometimes\n4) Not sure"
    ],
    "malaria": [
        "Have you recently traveled to a malaria-prone area?\n1) Yes\n2) No\n3) Not sure",
        "Do you have fever with chills and sweating?\n1) Yes, severe\n2) Yes, mild\n3) No\n4) Not sure"
    ],
    "dengue fever": [
        "Have you had a high fever recently?\n1) Yes, above 102°F\n2) Yes, mild fever\n3) No\n4) Not sure",
        "Do you have severe joint pain?\n1) Yes\n2) No\n3) Mild\n4) Not sure"
    ],
    "asthma": [
        "Do you experience difficulty breathing after exercise?\n1) Yes, always\n2) Yes, sometimes\n3) No\n4) Not sure",
        "Do you often wake up at night due to breathing issues?\n1) Yes, frequently\n2) Yes, sometimes\n3) No\n4) Not sure"
    ],
    "copd": [
        "Do you have a chronic cough with phlegm?\n1) Yes\n2) No\n3) Sometimes\n4) Not sure",
        "Do you feel breathless even at rest?\n1) Yes\n2) No\n3) Occasionally\n4) Not sure"
    ],
    "bronchitis": [
        "Have you been coughing up mucus for more than a week?\n1) Yes\n2) No\n3) Sometimes\n4) Not sure",
        "Do you experience wheezing while breathing?\n1) Yes\n2) No\n3) Occasionally\n4) Not sure"
    ],
    "hypertension": [
        "Have you had a blood pressure reading above 140/90 mmHg?\n1) Yes\n2) No\n3) Not sure\n4) Never checked",
        "Do you experience frequent headaches or dizziness?\n1) Yes\n2) No\n3) Sometimes\n4) Not sure"
    ],
    "chickenpox": [
        "Do you have an itchy rash with red spots?\n1) Yes\n2) No\n3) Mild\n4) Not sure",
        "Have you experienced fever before the rash appeared?\n1) Yes\n2) No\n3) Not sure"
    ],
    "measles": [
        "Do you have a high fever and cough?\n1) Yes\n2) No\n3) Mild\n4) Not sure",
        "Have you noticed white spots inside your mouth?\n1) Yes\n2) No\n3) Not sure"
    ],
    "covid-19": [
        "Have you experienced loss of taste or smell?\n1) Yes\n2) No\n3) Mild\n4) Not sure",
        "Do you have a persistent cough and fever?\n1) Yes\n2) No\n3) Sometimes\n4) Not sure"
    ],
    "hiv/aids": [
        "Have you experienced unexplained weight loss?\n1) Yes\n2) No\n3) Mild\n4) Not sure",
        "Do you have recurring fevers or night sweats?\n1) Yes\n2) No\n3) Sometimes\n4) Not sure"
    ],
    # --- Additional Diseases ---
    "allergic rhinitis": [
        "Do you experience frequent sneezing episodes?\n1) Yes, often\n2) Sometimes\n3) Rarely\n4) Not sure",
        "Do you have itchy, watery eyes?\n1) Yes, frequently\n2) Occasionally\n3) No\n4) Not sure",
        "Do you suffer from a runny or stuffy nose?\n1) Yes, continuously\n2) Yes, intermittently\n3) No\n4) Not sure"
    ],
    "appendicitis": [
        "Do you experience severe pain in the lower right abdomen?\n1) Yes\n2) No\n3) Not sure",
        "Does the pain worsen when you move or cough?\n1) Yes\n2) No\n3) Not sure",
        "Do you feel nauseated or have vomited recently?\n1) Yes, frequently\n2) Occasionally\n3) No\n4) Not sure"
    ],
    "arthritis": [
        "Do you have persistent joint pain?\n1) Yes, in multiple joints\n2) Yes, in a single joint\n3) No\n4) Not sure",
        "Do you experience stiffness in your joints, especially in the morning?\n1) Yes\n2) Sometimes\n3) No\n4) Not sure",
        "Does movement worsen your joint pain?\n1) Yes, significantly\n2) Moderately\n3) No\n4) Not sure"
    ],
    "hypothyroidism": [
        "Do you often feel tired or sluggish?\n1) Yes, all the time\n2) Sometimes\n3) No\n4) Not sure",
        "Have you experienced unexplained weight gain?\n1) Yes, significant\n2) Yes, slight\n3) No\n4) Not sure",
        "Are you sensitive to cold temperatures?\n1) Yes\n2) No\n3) Sometimes\n4) Not sure"
    ],
    "hyperthyroidism": [
        "Do you experience rapid heartbeat or palpitations?\n1) Yes, frequently\n2) Occasionally\n3) No\n4) Not sure",
        "Have you noticed unintentional weight loss?\n1) Yes, significant\n2) Yes, slight\n3) No\n4) Not sure",
        "Do you feel anxious or irritable more than usual?\n1) Yes, a lot\n2) Sometimes\n3) No\n4) Not sure"
    ],
    "urinary tract infection": [
        "Do you experience a burning sensation during urination?\n1) Yes, severe\n2) Yes, mild\n3) No\n4) Not sure",
        "Do you feel the need to urinate frequently?\n1) Yes, often\n2) Occasionally\n3) No\n4) Not sure",
        "Do you have lower abdominal pain?\n1) Yes\n2) No\n3) Sometimes\n4) Not sure"
    ],
    "kidney stones": [
        "Do you experience severe pain in your back or side?\n1) Yes, excruciating\n2) Yes, moderate\n3) No\n4) Not sure",
        "Have you noticed blood in your urine?\n1) Yes\n2) No\n3) Not sure",
        "Does the pain come in waves?\n1) Yes\n2) No\n3) Not sure"
    ],
    "anemia": [
        "Do you often feel unusually tired or weak?\n1) Yes, constantly\n2) Sometimes\n3) No\n4) Not sure",
        "Have you noticed a pale complexion?\n1) Yes\n2) No\n3) Not sure",
        "Do you experience shortness of breath during routine activities?\n1) Yes\n2) Occasionally\n3) No\n4) Not sure"
    ],
    "gastroenteritis": [
        "Do you have frequent diarrhea?\n1) Yes, severe\n2) Yes, mild\n3) No\n4) Not sure",
        "Have you experienced vomiting recently?\n1) Yes, repeatedly\n2) Yes, once or twice\n3) No\n4) Not sure",
        "Do you suffer from abdominal cramps?\n1) Yes, severe\n2) Yes, mild\n3) No\n4) Not sure"
    ],
    "sinusitis": [
        "Do you have facial pain or pressure around your nose and eyes?\n1) Yes, severe\n2) Yes, mild\n3) No\n4) Not sure",
        "Is your nasal congestion persistent?\n1) Yes\n2) Sometimes\n3) No\n4) Not sure",
        "Do you experience headaches due to sinus pressure?\n1) Yes, often\n2) Occasionally\n3) No\n4) Not sure"
    ]
}

# --- Utility Functions ---
def ask_gemini(prompt):
    # Use caching to avoid redundant calls
    if prompt in ai_cache:
        return ai_cache[prompt]
    try:
        model = genai.GenerativeModel('gemini-1.5-pro')
        response = model.generate_content(prompt)
        output = response.text if response.text else "Sorry, I couldn't generate a response."
        ai_cache[prompt] = output
        return output
    except Exception as e:
        return f"An error occurred while fetching AI recommendations: {e}"

def match_disease(user_input):
    diseases = list(disease_questions.keys())
    best_match, score = process.extractOne(user_input, diseases)
    return best_match if score > 60 else None

def clean_json_response(raw_json):
    cleaned = raw_json.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        cleaned = "\n".join(lines)
    cleaned = re.sub(r'//.*', '', cleaned)
    return cleaned.strip()

def save_consultation(user_id, symptoms, followup_responses, diagnosis):
    consultation = Consultation(
        user_id=user_id,
        symptoms=symptoms,
        followup_responses=json.dumps(followup_responses) if followup_responses else None,
        diagnosis=diagnosis
    )
    db.session.add(consultation)
    db.session.commit()

def send_confirmation_email(user_email):
    token = s.dumps(user_email, salt='email-confirm')
    confirm_url = url_for('confirm_email', token=token, _external=True)
    html = render_template_string("""
    <!doctype html>
    <html lang="en">
      <head>
        <meta charset="utf-8">
        <title>Email Confirmation</title>
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
      </head>
      <body>
        <div class="container mt-5">
          <div class="card">
            <div class="card-body">
              <h2>Email Confirmation</h2>
              <p>Please click the link below to confirm your email address:</p>
              <a href="{{ confirm_url }}" class="btn btn-primary">Confirm Email</a>
              <p class="mt-3 text-muted">This link will expire in 1 hour.</p>
            </div>
          </div>
        </div>
      </body>
    </html>
    """, confirm_url=confirm_url)
    try:
        msg = Message(subject="Please confirm your email", recipients=[user_email], html=html)
        mail.send(msg)
        return True
    except Exception as e:
        print(f"Error sending email: {e}")
        return False

# Simplified follow-up questions generator
def generate_followup_questions(symptoms_text):
    default_questions = [
        "How severe is your symptom on a scale of 1 to 10? (1) 1-3 (2) 4-6 (3) 7-9 (4) 10",
        "How long have you been experiencing this symptom? (1) Less than a day (2) 1-3 days (3) More than 3 days (4) Over a week",
        "Have you taken any medication for this condition? (1) Yes, it helped (2) Yes, no effect (3) No (4) Not sure",
        "Do you have any other symptoms? (1) Yes, related (2) Yes, unrelated (3) No (4) Not sure"
    ]
    return default_questions

# --- Routes ---
@app.route('/')
def index():
    return redirect(url_for('login'))

@app.route('/confirm/<token>')
def confirm_email(token):
    try:
        email = s.loads(token, salt='email-confirm', max_age=3600)
    except SignatureExpired:
        flash("The confirmation link has expired. Please register again.")
        return redirect(url_for('register'))
    except BadSignature:
        flash("Invalid confirmation token.")
        return redirect(url_for('register'))
    user = User.query.filter_by(email=email).first_or_404()
    if user.email_verified:
        flash("Account already verified. Please log in.")
    else:
        user.email_verified = True
        db.session.commit()
        flash("Email verified! You can now log in.")
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method=='POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        # Check if user exists
        user = User.query.filter_by(email=email).first()
        if not user:
            flash("Email not registered. Please create an account first.")
            return redirect(url_for('register'))
            
        # Check password
        if user.password == password:
            login_user(user)
            flash("Successfully logged in!")
            return redirect(url_for('dashboard'))
        else:
            flash("Invalid password. Please try again.")
            
    return render_template_string("""
    <!doctype html>
    <html lang="en">
      <head>
        <meta charset="utf-8">
        <title>Login</title>
        <link href="https://fonts.googleapis.com/css?family=Roboto:400,700&display=swap" rel="stylesheet">
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0-beta3/css/all.min.css">
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
        <style>
          body { font-family: 'Roboto', sans-serif; }
          .card { box-shadow: 0 4px 8px rgba(0,0,0,0.1); }
        </style>
      </head>
      <body class="bg-light">
        <div class="container">
          <div class="row justify-content-center mt-5">
            <div class="col-md-6">
              <div class="card">
                <div class="card-body">
                  <h3 class="card-title text-center"><i class="fas fa-user-md"></i> Login</h3>
                  {% with messages = get_flashed_messages() %}
                    {% if messages %}
                      {% for message in messages %}
                        <div class="alert alert-info">{{ message }}</div>
                      {% endfor %}
                    {% endif %}
                  {% endwith %}
                  <form method="post">
                    <div class="mb-3">
                      <label class="form-label">Email:</label>
                      <input type="email" class="form-control" name="email" required>
                    </div>
                    <div class="mb-3">
                      <label class="form-label">Password:</label>
                      <input type="password" class="form-control" name="password" required>
                    </div>
                    <button type="submit" class="btn btn-primary w-100">Login</button>
                  </form>
                  <p class="mt-3 text-center">Don't have an account? <a href="{{ url_for('register') }}">Register here</a></p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </body>
    </html>
    """)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method=='POST':
        email = request.form.get('email')
        password = request.form.get('password')
        if User.query.filter_by(email=email).first():
            flash("Email already registered! Please try logging in.")
            return redirect(url_for('register'))
        
        user = User(email=email, password=password, email_verified=True)
        db.session.add(user)
        db.session.commit()
        flash("Registration successful! You can now log in.")
        return redirect(url_for('login'))
        
    return render_template_string("""
    <!doctype html>
    <html lang="en">
      <head>
        <meta charset="utf-8">
        <title>Register</title>
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
      </head>
      <body class="bg-light">
        <div class="container">
          <div class="row justify-content-center mt-5">
            <div class="col-md-6">
              <div class="card">
                <div class="card-body">
                  <h3 class="card-title text-center">Register</h3>
                  {% with messages = get_flashed_messages() %}
                    {% if messages %}
                      {% for message in messages %}
                        <div class="alert alert-info">{{ message }}</div>
                      {% endfor %}
                    {% endif %}
                  {% endwith %}
                  <form method="post">
                    <div class="mb-3">
                      <label class="form-label">Email:</label>
                      <input type="email" class="form-control" name="email" required>
                    </div>
                    <div class="mb-3">
                      <label class="form-label">Password:</label>
                      <input type="password" class="form-control" name="password" required>
                    </div>
                    <button type="submit" class="btn btn-success w-100">Register</button>
                  </form>
                  <p class="mt-3 text-center">Already have an account? <a href="{{ url_for('login') }}">Login here</a></p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </body>
    </html>
    """)

@app.route('/create_test_user')
def create_test_user():
    test_email = "test@example.com"
    test_password = "password123"
    
    # Check if user already exists
    existing_user = User.query.filter_by(email=test_email).first()
    if existing_user:
        return f"Test user already exists with email: {test_email} and password: {test_password}"
        
    # Create a new test user
    test_user = User(email=test_email, password=test_password, email_verified=True)
    db.session.add(test_user)
    db.session.commit()
    
    # Create a user with the provided email if it's given in query parameters
    custom_email = request.args.get('email')
    custom_password = request.args.get('password', 'password123')
    
    if custom_email:
        custom_user = User(email=custom_email, password=custom_password, email_verified=True)
        db.session.add(custom_user)
        db.session.commit()
        return f"Created test user with email: {test_email} and password: {test_password}<br>Also created custom user with email: {custom_email} and password: {custom_password}"
    
    return f"Created test user with email: {test_email} and password: {test_password}"

@app.route('/list_users')
def list_users():
    users = User.query.all()
    result = "<h2>Registered Users</h2><ul>"
    for user in users:
        result += f"<li>Email: {user.email}, Password: {user.password}, Verified: {user.email_verified}</li>"
    result += "</ul>"
    return result

@app.route('/create_specific_user')
def create_specific_user():
    # Create the specific user mentioned in the issue
    specific_email = "gavindersingh164@gmail.com"
    specific_password = "password123"
    
    # Check if user already exists
    existing_user = User.query.filter_by(email=specific_email).first()
    if existing_user:
        # Update the password if user exists
        existing_user.password = specific_password
        existing_user.email_verified = True
        db.session.commit()
        return f"Updated user with email: {specific_email} and password: {specific_password}"
    
    # Create the user
    specific_user = User(email=specific_email, password=specific_password, email_verified=True)
    db.session.add(specific_user)
    db.session.commit()
    return f"Created user with email: {specific_email} and password: {specific_password}"

# --- Dashboard ---
@app.route('/dashboard', methods=['GET', 'POST'])
@login_required
def dashboard():
    if request.method == 'POST':
        symptoms = request.form.get("symptoms")
        session["symptoms"] = symptoms
        matched = match_disease(symptoms)
        session["matched_disease"] = matched
        
        # If a static disease match is found, redirect to followup
        if matched:
            return jsonify({"redirect": url_for("followup")})
        else:
            # If no match, generate analysis directly
            name = current_user.email
            prompt = (
                f"Patient: {name}. Symptoms: {symptoms}. "
                "Provide a detailed medical analysis in valid JSON format with no comments. "
                "Include: 'presenting_complaint', 'differential_diagnoses', 'investigations', "
                "'treatment', 'medications', 'precautions', and 'disclaimer'."
            )
            ai_response = ask_gemini(prompt)
            cleaned_response = clean_json_response(ai_response)
            try:
                analysis = json.loads(cleaned_response)
                save_consultation(current_user.id, symptoms, None, json.dumps(analysis))
                return jsonify({
                    "success": True,
                    "html": render_template_string(result_template, analysis=analysis)
                })
            except Exception as e:
                return jsonify({
                    "success": False,
                    "error": f"Failed to parse response: {str(e)}"
                })

    return render_template_string("""
    <!doctype html>
    <html lang="en">
      <head>
        <meta charset="utf-8">
        <title>Dashboard</title>
        <link href="https://fonts.googleapis.com/css?family=Roboto:400,700&display=swap" rel="stylesheet">
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0-beta3/css/all.min.css">
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
        <style>
          body { font-family: 'Roboto', sans-serif; }
          #sidebar { min-height: 100vh; background: #343a40; color: white; }
          #sidebar a { color: white; text-decoration: none; }
          .spinner-border { width: 3rem; height: 3rem; }
        </style>
      </head>
      <body class="bg-light">
        <div class="container-fluid">
          <div class="row">
            <!-- Sidebar -->
            <nav id="sidebar" class="col-md-2 d-none d-md-block bg-dark sidebar">
              <div class="position-sticky pt-3">
                <ul class="nav flex-column">
                  <li class="nav-item"><a class="nav-link active" href="{{ url_for('dashboard') }}"><i class="fas fa-tachometer-alt"></i> Dashboard</a></li>
                  <li class="nav-item"><a class="nav-link" href="{{ url_for('history') }}"><i class="fas fa-history"></i> History</a></li>
                  <li class="nav-item"><a class="nav-link" href="{{ url_for('hospital_locator') }}"><i class="fas fa-hospital"></i> Hospital Locator</a></li>
                  <li class="nav-item"><a class="nav-link" href="{{ url_for('appointment') }}"><i class="fas fa-calendar-alt"></i> Appointments</a></li>
                  <li class="nav-item"><a class="nav-link" href="{{ url_for('logout') }}"><i class="fas fa-sign-out-alt"></i> Logout</a></li>
                </ul>
              </div>
            </nav>
            <!-- Main Content -->
            <main class="col-md-10 ms-sm-auto col-lg-10 px-md-4">
              <h2 class="mt-4">Welcome, {{ current_user.email }}!</h2>
              <div id="alert-placeholder"></div>
              <div id="diagnosis-form-container">
                <form id="diagnosisForm" method="post">
                  <div class="mb-3">
                    <label for="symptoms" class="form-label">Describe your symptoms:</label>
                    <textarea class="form-control" id="symptoms" name="symptoms" rows="4" required></textarea>
                  </div>
                  <button type="submit" class="btn btn-primary">
                    <i class="fas fa-stethoscope"></i> Get Diagnosis
                  </button>
                </form>
              </div>
              <div id="diagnosis-result-container"></div>
              <!-- Loading Modal -->
              <div class="modal fade" id="loadingModal" tabindex="-1" aria-hidden="true">
                <div class="modal-dialog modal-dialog-centered">
                  <div class="modal-content">
                    <div class="modal-body text-center">
                      <div class="spinner-border text-primary" role="status">
                        <span class="visually-hidden">Loading...</span>
                      </div>
                      <p class="mt-3">Processing diagnosis...</p>
                    </div>
                  </div>
                </div>
              </div>
            </main>
          </div>
        </div>
        <script src="https://code.jquery.com/jquery-3.6.0.min.js"></script>
        <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/js/bootstrap.bundle.min.js"></script>
        <script>
          $(document).ready(function(){
            $('#diagnosisForm').submit(function(e){
              e.preventDefault();
              var formData = $(this).serialize();
              $('#loadingModal').modal('show');
              
              $.ajax({
                type: "POST",
                url: "{{ url_for('dashboard') }}",
                data: formData,
                success: function(response){
                  $('#loadingModal').modal('hide');
                  if (response.redirect) {
                    window.location.href = response.redirect;
                  } else if (response.success) {
                    $('#diagnosis-form-container').hide();
                    $('#diagnosis-result-container').html(response.html);
                  } else {
                    $('#alert-placeholder').html(
                      '<div class="alert alert-danger">' + response.error + '</div>'
                    );
                  }
                },
                error: function(){
                  $('#loadingModal').modal('hide');
                  $('#alert-placeholder').html(
                    '<div class="alert alert-danger">Error processing diagnosis. Please try again.</div>'
                  );
                }
              });
            });
          });
        </script>
      </body>
    </html>
    """)

# --- Follow-up Questions ---
@app.route("/followup", methods=["GET", "POST"])
@login_required
def followup():
    disease = session.get("matched_disease")
    symptoms = session.get("symptoms")
    
    # Use disease-specific questions or generate default ones
    if disease and disease in disease_questions:
        questions = disease_questions[disease]
    else:
        questions = generate_followup_questions(symptoms)
        
    if request.method == "POST":
        responses = []
        for i in range(len(questions)):
            responses.append(request.form.get(f"response{i}"))
            
        name = current_user.email
        prompt = (
            f"Patient: {name}. Symptoms: {symptoms}. "
            f"Follow-up responses: {responses}. "
            "Provide a detailed medical analysis in valid JSON format with no comments. "
            "Include: 'presenting_complaint', 'differential_diagnoses', 'investigations', "
            "'treatment', 'medications', 'precautions', and 'disclaimer'."
        )
        
        ai_response = ask_gemini(prompt)
        cleaned_response = clean_json_response(ai_response)
        
        try:
            analysis = json.loads(cleaned_response)
        except Exception as e:
            analysis = {"error": f"Failed to parse AI response: {str(e)}"}
            
        save_consultation(current_user.id, symptoms, responses, json.dumps(analysis))
        return render_template_string(result_template, analysis=analysis)
        
    return render_template_string(followup_template, disease=(disease if disease else "Your symptoms"), questions=questions)

# --- Consultation History ---
@app.route("/history")
@login_required
def history():
    consultations = Consultation.query.filter_by(user_id=current_user.id).order_by(Consultation.timestamp.desc()).all()
    
    # Prepare chart data
    dates = {}
    for c in consultations:
        date_str = c.timestamp.strftime("%Y-%m-%d")
        dates[date_str] = dates.get(date_str, 0) + 1
        
    chart_labels = list(dates.keys())
    chart_data = list(dates.values())
    
    return render_template_string("""
    <!doctype html>
    <html lang="en">
      <head>
        <meta charset="utf-8">
        <title>Consultation History</title>
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0-beta3/css/all.min.css">
        <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
      </head>
      <body class="bg-light">
        <div class="container">
          <h2 class="mt-5">Your Consultation History</h2>
          
          <!-- Flash Messages -->
          {% with messages = get_flashed_messages() %}
            {% if messages %}
              {% for message in messages %}
                <div class="alert alert-info">{{ message }}</div>
              {% endfor %}
            {% endif %}
          {% endwith %}
          
          {% if chart_labels %}
          <div class="card mt-4">
            <div class="card-header">
              <h4>Consultation Activity</h4>
            </div>
            <div class="card-body">
              <canvas id="historyChart" width="400" height="200"></canvas>
              <script>
                var ctx = document.getElementById('historyChart').getContext('2d');
                var historyChart = new Chart(ctx, {
                    type: 'bar',
                    data: {
                        labels: {{ chart_labels|tojson }},
                        datasets: [{
                            label: 'Number of Consultations',
                            data: {{ chart_data|tojson }},
                            backgroundColor: 'rgba(54, 162, 235, 0.5)',
                            borderColor: 'rgba(54, 162, 235, 1)',
                            borderWidth: 1
                        }]
                    },
                    options: { scales: { y: { beginAtZero: true } } }
                });
              </script>
            </div>
          </div>
          {% else %}
          <p>No consultation history found.</p>
          {% endif %}
          
          <h3 class="mt-5">Detailed History</h3>
          {% if consultations %}
          <div class="table-responsive">
            <table class="table table-striped">
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Symptoms</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {% for c in consultations %}
                <tr>
                  <td>{{ c.timestamp.strftime("%Y-%m-%d %H:%M") }}</td>
                  <td>{{ c.symptoms }}</td>
                  <td>
                    <a href="{{ url_for('download_pdf', consultation_id=c.id) }}" class="btn btn-sm btn-primary">
                      <i class="fas fa-download"></i> Download
                    </a>
                    <a href="{{ url_for('delete_consultation', consultation_id=c.id) }}" 
                       class="btn btn-sm btn-danger" 
                       onclick="return confirm('Are you sure you want to delete this record? This action cannot be undone.')">
                      <i class="fas fa-trash"></i> Delete
                    </a>
                  </td>
                </tr>
                {% endfor %}
              </tbody>
            </table>
          </div>
          {% else %}
          <p>No consultations found.</p>
          {% endif %}
          <br>
          <a href="{{ url_for('dashboard') }}" class="btn btn-primary">Back to Dashboard</a>
        </div>
      </body>
    </html>
    """, consultations=consultations, chart_labels=chart_labels, chart_data=chart_data)

@app.route("/delete_consultation/<int:consultation_id>")
@login_required
def delete_consultation(consultation_id):
    consultation = Consultation.query.filter_by(id=consultation_id, user_id=current_user.id).first_or_404()
    db.session.delete(consultation)
    db.session.commit()
    flash("Consultation record deleted successfully.")
    return redirect(url_for("history"))

@app.route("/download_pdf/<int:consultation_id>")
@login_required
def download_pdf(consultation_id):
    try:
        consultation = Consultation.query.filter_by(id=consultation_id, user_id=current_user.id).first_or_404()
        
        # Create a temporary file to store the PDF
        import tempfile
        temp = tempfile.NamedTemporaryFile(suffix='.pdf', delete=False)
        
        # Render PDF template
        html_content = render_template_string("""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>Medical Consultation Report</title>
            <style>
                body { font-family: Arial, sans-serif; line-height: 1.6; }
                .container { margin: 20px; }
                h1 { color: #2c3e50; }
                h5 { color: #34495e; margin-top: 20px; }
                .disclaimer { background-color: #fff3cd; padding: 10px; margin-top: 20px; }
            </style>
        </head>
        <body>
            <div class="container">
                <h1>Medical Consultation Report</h1>
                <p><strong>Date:</strong> {{ consultation.timestamp.strftime('%Y-%m-%d %H:%M') }}</p>
                <p><strong>Patient:</strong> {{ current_user.email }}</p>
                
                <h5>Presenting Complaint</h5>
                <p>{{ analysis.get('presenting_complaint', 'Not available') }}</p>
                
                <h5>Differential Diagnoses</h5>
                <p>{{ analysis.get('differential_diagnoses', 'Not available') }}</p>
                
                <h5>Investigations</h5>
                <p>{{ analysis.get('investigations', 'Not available') }}</p>
                
                <h5>Treatment</h5>
                <p>{{ analysis.get('treatment', 'Not available') }}</p>
                
                <h5>Medications/Prescription</h5>
                <p>{{ analysis.get('medications', 'Not available') }}</p>
                
                <h5>Precautions</h5>
                <p>{{ analysis.get('precautions', 'Not available') }}</p>
                
                <div class="disclaimer">
                    <h5>Disclaimer</h5>
                    <p>{{ analysis.get('disclaimer', 'This is an AI-generated analysis and should not replace professional medical advice. Please consult a healthcare provider for proper diagnosis and treatment.') }}</p>
                </div>
            </div>
        </body>
        </html>
        """, analysis=json.loads(consultation.diagnosis), consultation=consultation)

        # Generate PDF
        pdfkit.from_string(
            html_content,
            temp.name,
            configuration=PDFKIT_CONFIG,
            options=PDF_OPTIONS
        )

        # Send the file
        return send_file(
            temp.name,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=f'consultation_report_{consultation.timestamp.strftime("%Y%m%d")}.pdf'
        )

    except Exception as e:
        flash(f"Error generating PDF: {str(e)}")
        return redirect(url_for('history'))

# --- Hospital Locator ---
@app.route("/hospital_locator", methods=["GET"])
@login_required
def hospital_locator():
    city = request.args.get('city')
    if city:
        try:
            geolocator = Nominatim(user_agent="hospital_locator")
            location = geolocator.geocode(city)
            if location:
                lat, lon = location.latitude, location.longitude
                m = folium.Map(location=[lat, lon], zoom_start=13)
                folium.Marker([lat, lon], popup=f"Main Hospital in {city}").add_to(m)
                folium.Marker([lat + 0.01, lon + 0.01], popup="Secondary Hospital").add_to(m)
                folium.Marker([lat - 0.01, lon - 0.01], popup="Community Hospital").add_to(m)
                map_html = m._repr_html_()
                return render_template_string("""
                <!doctype html>
                <html lang="en">
                  <head>
                    <meta charset="utf-8">
                    <title>Hospital Locator</title>
                    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
                  </head>
                  <body class="bg-light">
                    <div class="container">
                      <h2 class="mt-5">Hospital Locator for {{ city }}</h2>
                      <div class="mt-4">
                        {{ map_html|safe }}
                      </div>
                      <br>
                      <a href="{{ url_for('dashboard') }}" class="btn btn-primary mt-3">Back to Dashboard</a>
                    </div>
                  </body>
                </html>
                """, map_html=map_html, city=city)
            else:
                flash("City not found. Please try again.")
                return redirect(url_for('hospital_locator'))
        except Exception as e:
            flash(f"Error occurred: {str(e)}")
            return redirect(url_for('dashboard'))
    else:
        return render_template_string("""
        <!doctype html>
        <html lang="en">
          <head>
            <meta charset="utf-8">
            <title>Hospital Locator</title>
            <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
          </head>
          <body class="bg-light">
            <div class="container">
              <h2 class="mt-5">Hospital Locator</h2>
              <form method="get" action="{{ url_for('hospital_locator') }}">
                <div class="mb-3">
                  <label for="city" class="form-label">Enter your city:</label>
                  <input type="text" class="form-control" name="city" id="city" required>
                </div>
                <button type="submit" class="btn btn-primary">Search</button>
              </form>
              <br>
              <a href="{{ url_for('dashboard') }}" class="btn btn-primary">Back to Dashboard</a>
            </div>
          </body>
        </html>
        """)

@app.route("/appointment", methods=["GET", "POST"])
@login_required
def appointment():
    # Get user's existing appointments
    user_appointments = Appointment.query.filter_by(user_id=current_user.id).order_by(Appointment.date, Appointment.time).all()
    
    if request.method == "POST":
        # Collect form data
        date_str = request.form.get("date")
        time = request.form.get("time")
        doctor = request.form.get("doctor")
        notes = request.form.get("notes", "")
        
        # Convert string date to datetime.date object
        try:
            date_obj = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
            
            # Create new appointment
            new_appointment = Appointment(
                date=date_obj,
                time=time,
                doctor=doctor,
                notes=notes,
                user_id=current_user.id
            )
            
            db.session.add(new_appointment)
            db.session.commit()
            flash("Appointment scheduled successfully!")
            return redirect(url_for("appointment"))
            
        except ValueError:
            flash("Invalid date format. Please use YYYY-MM-DD format.")
            
    return render_template_string("""
    <!doctype html>
    <html lang="en">
      <head>
        <meta charset="utf-8">
        <title>Schedule Appointment</title>
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0-beta3/css/all.min.css">
      </head>
      <body class="bg-light">
        <div class="container">
          <h2 class="mt-5">Manage Appointments</h2>
          
          <!-- Flash Messages -->
          {% with messages = get_flashed_messages() %}
            {% if messages %}
              {% for message in messages %}
                <div class="alert alert-info">{{ message }}</div>
              {% endfor %}
            {% endif %}
          {% endwith %}
          
          <!-- Schedule New Appointment Form -->
          <div class="card mt-4">
            <div class="card-header">
              <h4>Schedule New Appointment</h4>
            </div>
            <div class="card-body">
              <form method="post">
                <div class="mb-3">
                  <label class="form-label">Date:</label>
                  <input type="date" class="form-control" name="date" required>
                </div>
                <div class="mb-3">
                  <label class="form-label">Time:</label>
                  <input type="time" class="form-control" name="time" required>
                </div>
                <div class="mb-3">
                  <label class="form-label">Doctor's Name:</label>
                  <input type="text" class="form-control" name="doctor" required>
                </div>
                <div class="mb-3">
                  <label class="form-label">Notes (optional):</label>
                  <textarea class="form-control" name="notes" rows="3"></textarea>
                </div>
                <button type="submit" class="btn btn-success">Schedule Appointment</button>
              </form>
            </div>
          </div>
          
          <!-- Existing Appointments -->
          <div class="card mt-4">
            <div class="card-header">
              <h4>Your Scheduled Appointments</h4>
            </div>
            <div class="card-body">
              {% if appointments %}
                <div class="table-responsive">
                  <table class="table table-striped">
                    <thead>
                      <tr>
                        <th>Date</th>
                        <th>Time</th>
                        <th>Doctor</th>
                        <th>Notes</th>
                        <th>Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {% for apt in appointments %}
                        <tr>
                          <td>{{ apt.date.strftime('%Y-%m-%d') }}</td>
                          <td>{{ apt.time }}</td>
                          <td>{{ apt.doctor }}</td>
                          <td>{{ apt.notes if apt.notes else 'N/A' }}</td>
                          <td>
                            <a href="{{ url_for('delete_appointment', appointment_id=apt.id) }}" 
                               class="btn btn-sm btn-danger" 
                               onclick="return confirm('Are you sure you want to cancel this appointment?')">
                              <i class="fas fa-trash"></i> Cancel
                            </a>
                          </td>
                        </tr>
                      {% endfor %}
                    </tbody>
                  </table>
                </div>
              {% else %}
                <p>You don't have any scheduled appointments.</p>
              {% endif %}
            </div>
          </div>
          
          <br>
          <a href="{{ url_for('dashboard') }}" class="btn btn-primary">Back to Dashboard</a>
        </div>
      </body>
    </html>
    """, appointments=user_appointments)

@app.route("/delete_appointment/<int:appointment_id>")
@login_required
def delete_appointment(appointment_id):
    appointment = Appointment.query.filter_by(id=appointment_id, user_id=current_user.id).first_or_404()
    db.session.delete(appointment)
    db.session.commit()
    flash("Appointment canceled successfully!")
    return redirect(url_for("appointment"))

# --- Templates for Diagnosis Result and Follow-up ---
result_template = """
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <title>Diagnosis Result</title>
    <link href="https://fonts.googleapis.com/css?family=Roboto:400,700&display=swap" rel="stylesheet">
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
      body { font-family: 'Roboto', sans-serif; }
    </style>
  </head>
  <body class="bg-light">
    <div class="container">
      <h2 class="mt-5">Medical Analysis</h2>
      <div class="card">
        <div class="card-body">
          <h5>Presenting Complaint</h5>
          <p>{{ analysis.get('presenting_complaint', 'Not available') }}</p>
          <h5>Differential Diagnoses</h5>
          <p>{{ analysis.get('differential_diagnoses', 'Not available') }}</p>
          <h5>Investigations</h5>
          <p>{{ analysis.get('investigations', 'Not available') }}</p>
          <h5>Treatment</h5>
          <p>{{ analysis.get('treatment', 'Not available') }}</p>
          <h5>Medications/Prescription</h5>
          <p>{{ analysis.get('medications', 'Not available') }}</p>
          <h5>Precautions</h5>
          <p>{{ analysis.get('precautions', 'Not available') }}</p>
          <div class="alert alert-warning">
            <h5>Disclaimer</h5>
            <p>{{ analysis.get('disclaimer', 'This is an AI-generated analysis and should not replace professional medical advice. Consult a healthcare provider for proper diagnosis and treatment.') }}</p>
          </div>
          <!-- Feedback Form -->
          <div class="mt-4">
            <h6>Rate the accuracy of this diagnosis:</h6>
            <form id="feedbackForm">
              <select class="form-select" id="rating" required>
                <option value="">Select a rating</option>
                <option value="1">1 - Very Poor</option>
                <option value="2">2 - Poor</option>
                <option value="3">3 - Average</option>
                <option value="4">4 - Good</option>
                <option value="5">5 - Excellent</option>
              </select>
              <br>
              <button type="button" class="btn btn-outline-primary" onclick="submitFeedback()">Submit Feedback</button>
            </form>
          </div>
        </div>
      </div>
      <a href="{{ url_for('dashboard') }}" class="btn btn-primary mt-3">Back to Dashboard</a>
    </div>
    <script>
      function submitFeedback() {
        var rating = document.getElementById('rating').value;
        alert("Thank you for rating this diagnosis: " + rating + " stars!");
      }
    </script>
  </body>
</html>
"""

followup_template = """
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <title>Follow-up Questions</title>
    <link href="https://fonts.googleapis.com/css?family=Roboto:400,700&display=swap" rel="stylesheet">
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
      body { font-family: 'Roboto', sans-serif; }
    </style>
  </head>
  <body class="bg-light">
    <div class="container">
      <h2 class="mt-5">Follow-up Questions for {{ disease }}</h2>
      <form method="post">
        {% for question in questions %}
        <div class="mb-3">
          <label class="form-label">{{ question }}</label>
          <select class="form-select" name="response{{ loop.index0 }}" required>
            <option value="">Select an answer</option>
            <option value="1">Option 1</option>
            <option value="2">Option 2</option>
            <option value="3">Option 3</option>
            <option value="4">Option 4</option>
          </select>
        </div>
        {% endfor %}
        <button type="submit" class="btn btn-primary">Submit</button>
      </form>
      <a href="{{ url_for('dashboard') }}" class="btn btn-secondary mt-3">Back to Dashboard</a>
    </div>
  </body>
</html>
"""

if __name__ == "__main__":
    app.run(debug=True, host='127.0.0.1', port=5000)
