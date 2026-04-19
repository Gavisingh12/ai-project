import os

from app import create_app
from app.extensions import db, mail
from app.models import Appointment, Consultation, User


app = create_app()


if __name__ == "__main__":
    app.run(
        debug=app.config["DEBUG"],
        host=os.environ.get("HOST", "0.0.0.0"),
        port=int(os.environ.get("PORT", 5000))
    )
