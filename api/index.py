"""Explicit Vercel Function entry point for the Flask application."""

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from main2 import app as flask_app


class VercelPathFix:
    """Strip Vercel rewrite prefix so Flask routing sees the real path.

    vercel.json rewrites /(.*) -> /api/index, so without this Flask sees
    PATH_INFO=/api/index for every request and returns 404.
    """

    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        path = environ.get("PATH_INFO", "") or ""
        if path == "/api/index" or path == "/api/index/":
            environ["PATH_INFO"] = "/"
        elif path.startswith("/api/index/"):
            environ["PATH_INFO"] = path[len("/api/index"):]
        return self.app(environ, start_response)


app = VercelPathFix(flask_app)
