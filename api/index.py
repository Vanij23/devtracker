"""
Entry point for Vercel's Python runtime.
Vercel looks for a WSGI-compatible `app` object in api/index.py and routes
all requests here (see vercel.json's rewrite rule).
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app  # noqa: E402
