# CareCompass AI

CareCompass AI is a Flask-based medical support dashboard for symptom intake, guided follow-up, consultation history, PDF export, appointment planning, password reset, and hospital lookup.

## Features

- Account signup with email verification
- Login with email or name
- AI-assisted consultation analysis with safe fallback mode
- Follow-up question flow based on symptom matching
- Consultation history with charting and PDF downloads
- Appointment scheduling and cancellation
- Hospital locator with map view
- Password reset flow
- Health-check endpoint for deployment monitoring

## Stack

- Python 3.13
- Flask
- SQLAlchemy
- Flask-Login
- Flask-Mail
- Google Gemini API
- Folium and Geopy
- RapidFuzz
- Waitress
- Pytest

## Local Setup

1. Install dependencies:
   ```powershell
   pip install -r requirements.txt
   ```
2. Copy the environment template:
   ```powershell
   Copy-Item .env.example .env
   ```
3. Update `.env` with your values.
4. Run the app:
   ```powershell
   python main2.py
   ```
5. Open [http://localhost:5000](http://localhost:5000) and check [http://localhost:5000/health](http://localhost:5000/health).

## Important Environment Variables

- `FLASK_SECRET_KEY`: required in all environments
- `DATABASE_URL`: required in production and should point to PostgreSQL
- `GEMINI_API_KEY`: optional, enables richer AI responses
- `MAIL_USERNAME`: required in production for verification email
- `MAIL_PASSWORD`: required in production for verification email
- `MAIL_DEFAULT_SENDER`: required in production for verification email
- `SESSION_COOKIE_SECURE`: should be `true` in production
- `REMEMBER_COOKIE_SECURE`: should be `true` in production
- `ENABLE_DEV_ROUTES`: keep `false` in production

## Production Readiness Notes

- The app now blocks unsafe production startup when required settings are missing.
- SQLite is only for local development; production should use PostgreSQL.
- Email verification is part of the signup flow, so mail settings must be configured in production.
- The app includes a built-in PDF fallback, so PDF export still works without `wkhtmltopdf`.
- Waitress is included for production startup.

## Render Deployment

This repository now includes a [render.yaml](render.yaml) Blueprint file.

### What it provisions

- One Python web service
- One Render Postgres database
- Health check on `/health`
- Generated `FLASK_SECRET_KEY`
- Secure cookie settings for production

### Plan note

- The included Blueprint now uses a paid-safe setup: `starter` for the web service and `basic-256mb` for Postgres.
- Render's official free-tier docs say Free web services spin down after 15 minutes of idle time, Free web services cannot send outbound SMTP traffic on ports such as `587`, and Free Postgres is not intended for production use.
- Because this app uses email verification, free-tier web services are not a good fit for the current mail flow.

### Environment values you still need to set in Render

- `GEMINI_API_KEY`
- `MAIL_USERNAME`
- `MAIL_PASSWORD`
- `MAIL_DEFAULT_SENDER`

### Local verification note

- On `localhost`, if mail credentials are not configured yet, the app now shows a local verification button instead of blocking signup.
- On the live deployment, real mail credentials are still required so account confirmation reaches the user's inbox.

### Deploy steps

1. Push this repository to GitHub.
2. Log in to Render.
3. Create a new Blueprint and connect this repository.
4. Render will read `render.yaml` and create the web service plus database.
5. Add the missing secret environment values in the Render dashboard.
6. Trigger a deploy and wait for the health check to pass.

## Testing

```powershell
pip install -r requirements-dev.txt
pytest -q
```

## Docker

```powershell
docker build -t carecompass-ai .
docker run -p 8000:8000 --env-file .env carecompass-ai
```

## Disclaimer

This project is an educational AI application and must not be treated as a substitute for licensed medical advice, diagnosis, or treatment.
