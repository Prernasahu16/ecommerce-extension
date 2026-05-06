# ============================================================
# EXTENSION — auth/jwt_auth.py
# Stateless JWT authentication layer.
# Keeps localStorage session as fallback (no breakage).
# Requires: pip install PyJWT bcrypt
# Env vars:  JWT_SECRET_KEY, JWT_EXPIRY_HOURS (default 24)
# ============================================================

import os
import logging
import hashlib
import hmac
from datetime import datetime, timedelta, timezone

log = logging.getLogger(__name__)

JWT_SECRET   = os.getenv("JWT_SECRET_KEY", "change-me-in-production-32chars+")
JWT_EXPIRY_H = int(os.getenv("JWT_EXPIRY_HOURS", 24))
ALGORITHM    = "HS256"


# -------------------------------------------------------
# INTERNAL: pure-Python HS256 JWT (no PyJWT dependency)
# Avoids hard dependency — falls back gracefully if bcrypt
# is also missing. Production should install PyJWT.
# -------------------------------------------------------
import base64, json as _json, struct as _struct, time as _time


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64url_decode(s: str) -> bytes:
    pad = 4 - len(s) % 4
    return base64.urlsafe_b64decode(s + "=" * (pad % 4))


def _create_jwt(payload: dict) -> str:
    header  = _b64url_encode(_json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    body    = _b64url_encode(_json.dumps(payload).encode())
    msg     = f"{header}.{body}".encode()
    sig     = hmac.new(JWT_SECRET.encode(), msg, hashlib.sha256).digest()
    return f"{header}.{body}.{_b64url_encode(sig)}"


def _verify_jwt(token: str) -> dict | None:
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        header, body, sig = parts
        msg         = f"{header}.{body}".encode()
        expected    = hmac.new(JWT_SECRET.encode(), msg, hashlib.sha256).digest()
        if not hmac.compare_digest(_b64url_decode(sig), expected):
            return None
        payload = _json.loads(_b64url_decode(body))
        if payload.get("exp", 0) < _time.time():
            return None
        return payload
    except Exception:
        return None


# -------------------------------------------------------
# PUBLIC API
# -------------------------------------------------------
def generate_token(user_id: str, email: str, role: str = "user") -> str:
    payload = {
        "sub":   user_id,
        "email": email,
        "role":  role,
        "iat":   int(_time.time()),
        "exp":   int(_time.time()) + JWT_EXPIRY_H * 3600,
    }
    return _create_jwt(payload)


def decode_token(token: str) -> dict | None:
    """Returns payload dict or None if invalid/expired."""
    return _verify_jwt(token)


def hash_password(plain: str) -> str:
    """SHA-256 + secret pepper. Use bcrypt in production."""
    pepper = os.getenv("PASSWORD_PEPPER", "ext-pepper-change-me")
    return hashlib.sha256(f"{plain}{pepper}".encode()).hexdigest()


def verify_password(plain: str, hashed: str) -> bool:
    return hmac.compare_digest(hash_password(plain), hashed)


# -------------------------------------------------------
# FLASK DECORATOR — extracts JWT or falls back to session_id
# -------------------------------------------------------
from functools import wraps
from flask import request, g


def resolve_identity(f):
    """
    Decorator that populates g.user_id from:
      1. Authorization: Bearer <jwt>  → verified JWT sub claim
      2. X-Session-Id header          → raw session string (localStorage fallback)
      3. ?session_id= query param     → same fallback

    Never raises — unauthed requests get g.user_id = None.
    Protected routes check g.user_id themselves.
    """
    @wraps(f)
    def wrapper(*args, **kwargs):
        g.user_id   = None
        g.auth_type = "none"

        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token   = auth_header[7:]
            payload = decode_token(token)
            if payload:
                g.user_id   = payload["sub"]
                g.auth_type = "jwt"
        
        if not g.user_id:
            sid = (request.headers.get("X-Session-Id") or
                   request.args.get("session_id") or
                   (request.get_json(silent=True) or {}).get("session_id"))
            if sid:
                g.user_id   = sid
                g.auth_type = "session"

        return f(*args, **kwargs)
    return wrapper


def require_jwt(f):
    """Strict decorator — rejects requests without a valid JWT."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            from flask import jsonify
            return jsonify({"success": False, "error": "JWT required"}), 401
        payload = decode_token(auth_header[7:])
        if not payload:
            from flask import jsonify
            return jsonify({"success": False, "error": "Invalid or expired token"}), 401
        g.user_id   = payload["sub"]
        g.auth_type = "jwt"
        return f(*args, **kwargs)
    return wrapper
