# Setup Guide

## Local Development

1. Install dependencies:
   ```powershell
   pip install -r requirements.txt
   ```
2. Copy the environment template:
   ```powershell
   Copy-Item .env.example .env
   ```
3. Update `.env` with:
   - `FLASK_SECRET_KEY`
   - optional `GEMINI_API_KEY`
   - optional mail credentials for real inbox delivery
   - optional `WKHTMLTOPDF_PATH`
4. Start the app:
   ```powershell
   python main2.py
   ```
5. Open:
   - `http://localhost:5000`
   - `http://localhost:5000/health`

## Live Deployment Checklist

1. Push the latest code to GitHub.
2. Create a Gmail App Password if you want real account verification emails.
3. In Render, deploy the repository as a Blueprint using `render.yaml`.
4. Add these Render secrets:
   - `MAIL_USERNAME`
   - `MAIL_PASSWORD`
   - `MAIL_DEFAULT_SENDER`
   - `GEMINI_API_KEY`
5. Wait for the Render health check on `/health` to pass.
6. Create a fresh account on the live site and verify that the confirmation email arrives.

## Production Preflight

Run this before a live launch:

```powershell
python scripts/deploy_preflight.py --production
```

What it checks:

- strong `FLASK_SECRET_KEY`
- PostgreSQL `DATABASE_URL`
- secure cookies enabled
- dev routes disabled
- required mail settings present
- optional AI key warning

## Gmail Setup

- Turn on 2-Step Verification for your Google account.
- Generate a Google App Password.
- Use that App Password as `MAIL_PASSWORD`.
- Keep `MAIL_USERNAME` and `MAIL_DEFAULT_SENDER` aligned to the same mailbox.

## Application Layout

- `main2.py` runs the local Flask server.
- `wsgi.py` exposes the production app object.
- `app/routes/` contains route blueprints.
- `app/services/` contains AI, PDF, and hospital helper logic.
- `app/templates/` contains the rendered frontend pages.

## Automated Testing

1. Install dev dependencies:
   ```powershell
   pip install -r requirements-dev.txt
   ```
2. Run the test suite:
   ```powershell
   pytest -q
   ```

## Production Notes

- The app reads `DATABASE_URL` for production databases and defaults to local SQLite during development.
- Localhost can use the local verification button when mail is not configured.
- Live deployments must use real mail credentials for account verification.
- Waitress is included for production serving.
- PDF export remains available even when `wkhtmltopdf` is missing because a built-in fallback is included.
