"""Entry point for running from the project root.

Hosting platforms start the app from the repository root, but the code lives in
backend/app. This file bridges the two: it puts backend/ on the import path and
exposes `app` where a server expects to find it.

    gunicorn wsgi:app          (production)
    python wsgi.py             (local, same as before)
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "backend"))

from app.main import app      # noqa: E402  (import must follow the path setup)

if __name__ == "__main__":
    app.run(port=8000, debug=True)
