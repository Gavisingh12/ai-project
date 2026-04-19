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
   - `GEMINI_API_KEY`
   - optional mail credentials
   - optional `WKHTMLTOPDF_PATH` if PDF export is needed

4. Start the app:
   ```powershell
   python main2.py
   ```

5. Check runtime health:
   - Open `http://localhost:5000/health`

## Application Layout

- `main2.py` is the local run entrypoint.
- `app/routes/` contains route blueprints.
- `app/services/` contains AI, PDF, and hospital helper logic.
- `app/templates/` contains the rendered frontend pages.
- `app/static/` contains the recruiter-facing UI assets.

## Automated Testing

1. Install dev dependencies:
   ```powershell
   pip install -r requirements-dev.txt
   ```

2. Run the test suite:
   ```powershell
   pytest
   ```

## Production Notes

- The app reads `DATABASE_URL` for production databases and defaults to `instance/app.db` locally.
- Dev helper routes stay disabled unless `ENABLE_DEV_ROUTES=True`.
- CSRF protection is enabled on mutating requests.
- Waitress is included for production serving.
- PDF export remains optional and activates automatically when `wkhtmltopdf` is available.
- Password reset works with configured mail credentials and supports local debugging when dev routes are enabled.
