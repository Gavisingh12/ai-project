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
2. In Render, deploy the repository as a Blueprint using `render.yaml`.
3. Keep `REQUIRE_EMAIL_VERIFICATION=False` for the free demo deployment.
4. Add `GEMINI_API_KEY` only if you want richer AI responses.
5. Wait for the Render health check on `/health` to pass.
6. Create a fresh account on the live site and sign in directly without inbox confirmation.
7. Remember that Render free Postgres is temporary and the free web service can spin down when idle.

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
- mail settings only when email verification is enabled
- optional AI key warning

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
- Email verification is disabled by default so the free public demo can run without SMTP.
- If you later turn `REQUIRE_EMAIL_VERIFICATION=True`, you must also configure the mail variables.
- Waitress is included for production serving.
- PDF export remains available even when `wkhtmltopdf` is missing because a built-in fallback is included.
