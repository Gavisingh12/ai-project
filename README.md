# CareCompass AI

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/Gavisingh12/ai-project)

CareCompass AI is a Flask-based medical support dashboard for symptom intake, guided follow-up, consultation history, PDF export, appointment planning, password reset, and hospital lookup.

## Features

- Account signup with direct demo access
- Login with email or name
- AI-assisted consultation analysis with safe fallback mode
- Follow-up question flow based on symptom matching
- Consultation history with charting and PDF downloads
- Appointment scheduling and cancellation
- Hospital locator with map view
- Password reset flow when mail is configured
- Health-check endpoint for deployment monitoring
- SEO-ready metadata, sitemap, robots, favicon, and social share card
- Optional Google Analytics and Sentry monitoring via environment variables

## Recruiter Snapshot

CareCompass AI is a production-minded Flask application that turns symptom intake into a cleaner clinical support workflow. It combines structured AI output, consultation history, appointment planning, PDF reports, health monitoring, and deployable infrastructure in one polished demo.

## Resume-Ready Description

- Built and deployed a full-stack Flask healthcare support dashboard with AI-assisted symptom analysis, PDF reporting, hospital discovery, and appointment planning.
- Designed a polished recruiter-facing UI with structured clinical summaries, responsive dashboard layouts, SEO metadata, and production-ready observability hooks.
- Prepared the application for cloud deployment with PostgreSQL, environment-based configuration, health checks, and optional analytics and error monitoring.

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
- `REQUIRE_EMAIL_VERIFICATION`: keep `false` for the free public demo
- `MAIL_USERNAME`: optional unless email verification is enabled
- `MAIL_PASSWORD`: optional unless email verification is enabled
- `MAIL_DEFAULT_SENDER`: optional unless email verification is enabled
- `SITE_URL`: optional custom domain or canonical base URL
- `GA_MEASUREMENT_ID`: optional Google Analytics 4 measurement ID
- `SENTRY_DSN`: optional Sentry DSN for production error monitoring
- `SESSION_COOKIE_SECURE`: should be `true` in production
- `REMEMBER_COOKIE_SECURE`: should be `true` in production
- `ENABLE_DEV_ROUTES`: keep `false` in production

## Production Readiness Notes

- The app now blocks unsafe production startup when required settings are missing.
- SQLite is only for local development; production should use PostgreSQL.
- Email verification is now optional and disabled by default for free public demo deployments.
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

- The included Blueprint now targets a free public demo: `free` for the web service and `free` for Postgres.
- Email verification is disabled in the Blueprint, so signup works without SMTP.
- Free Render web services spin down after 15 minutes of idle time and free Render Postgres databases expire 30 days after creation.

### Environment values you still need to set in Render

- `GEMINI_API_KEY`
- `SITE_URL` if you add a custom domain later
- `GA_MEASUREMENT_ID` if you want Google Analytics
- `SENTRY_DSN` if you want production error monitoring

### Deploy steps

1. Push this repository to GitHub.
2. Log in to Render.
3. Create a new Blueprint and connect this repository.
4. Render will read `render.yaml` and create the web service plus database.
5. Add `GEMINI_API_KEY` in the Render dashboard if you want richer AI responses.
6. Trigger a deploy and wait for the health check to pass.
7. Use the live site as a public demo with direct sign-up and no inbox confirmation.

### Preflight check

Before going live, you can validate your local production-style environment with:

```powershell
python scripts/deploy_preflight.py --production
```

The script reports missing secrets, insecure cookie settings, SQLite usage, and optional AI warnings before you deploy.

## Custom Domain And Monitoring

- Add your domain in Render, then set `SITE_URL` to that final `https://` address.
- Add `GA_MEASUREMENT_ID` to enable Google Analytics 4 page tracking.
- Add `SENTRY_DSN` to enable Sentry-based production error monitoring.

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
