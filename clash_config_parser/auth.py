import os
import functools
from flask import request, session, redirect, url_for, jsonify

ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")


def login_required(f):
    """Decorator: require session auth for admin routes."""
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        if not ADMIN_PASSWORD:
            return f(*args, **kwargs)
        if session.get("authenticated"):
            return f(*args, **kwargs)
        if request.is_json or request.path.startswith("/api/"):
            return jsonify({"error": "unauthorized"}), 401
        return redirect(url_for("login_page"))
    return wrapper
