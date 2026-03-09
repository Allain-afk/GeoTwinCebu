"""
Vercel entry point.
Vercel's Python runtime looks for a WSGI-compatible `app` object in api/index.py.
We add the project root to sys.path so the `app` package is importable.
"""
import sys
import os
from pathlib import Path

# Make the project root importable
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))

# Load .env when running locally (no-op in Vercel where env vars are set in dashboard)
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass

from app import app  # noqa: E402  — Flask app object
