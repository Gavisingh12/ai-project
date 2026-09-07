"""One-time database initialization for a production PostgreSQL deployment."""

from app import create_app, initialize_database


app = create_app()

with app.app_context():
    initialize_database(app)
    print("Database schema is ready.")
