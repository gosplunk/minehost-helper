from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import time
from typing import Any

from .storage import auth_store

PBKDF2_ITERATIONS = 260_000
SESSION_SECONDS = 7 * 24 * 60 * 60
COOKIE_NAME = "minehost_session"


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _hash_password(password: str, salt: bytes | None = None) -> dict[str, Any]:
    salt = salt or os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return {
        "algorithm": "pbkdf2_sha256",
        "iterations": PBKDF2_ITERATIONS,
        "salt": _b64(salt),
        "hash": _b64(digest),
    }


def _decode_b64(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _clean_username(username: str) -> str:
    cleaned = username.strip()
    if not 3 <= len(cleaned) <= 32:
        raise ValueError("Username must be 3 to 32 characters.")
    if not all(char.isalnum() or char in "._-" for char in cleaned):
        raise ValueError("Username can use letters, numbers, dots, dashes, and underscores.")
    return cleaned


def _validate_password(password: str) -> None:
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters.")


def configured() -> bool:
    data = auth_store.read({})
    return bool(data.get("username") and data.get("password"))


def status() -> dict[str, Any]:
    data = auth_store.read({})
    return {
        "configured": configured(),
        "username": data.get("username") if configured() else None,
    }


def setup(username: str, password: str, overwrite: bool = False) -> dict[str, Any]:
    if configured() and not overwrite:
        raise ValueError("A web login already exists.")
    cleaned_username = _clean_username(username)
    _validate_password(password)
    current = auth_store.read({})
    current.update({
        "username": cleaned_username,
        "password": _hash_password(password),
        "sessions": {},
        "updated_at": time.time(),
    })
    auth_store.write(current)
    return status()


def verify(username: str, password: str) -> bool:
    data = auth_store.read({})
    password_data = data.get("password") or {}
    if username != data.get("username"):
        return False
    try:
        salt = _decode_b64(password_data["salt"])
        expected = _decode_b64(password_data["hash"])
        iterations = int(password_data.get("iterations", PBKDF2_ITERATIONS))
    except Exception:
        return False
    actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(actual, expected)


def create_session(username: str, password: str) -> str:
    if not verify(username, password):
        raise ValueError("Username or password is incorrect.")
    token = secrets.token_urlsafe(32)
    data = auth_store.read({})
    sessions = _pruned_sessions(data.get("sessions") or {})
    sessions[_token_hash(token)] = time.time() + SESSION_SECONDS
    data["sessions"] = sessions
    auth_store.write(data)
    return token


def _pruned_sessions(sessions: dict[str, Any]) -> dict[str, float]:
    now = time.time()
    pruned: dict[str, float] = {}
    for key, expires_at in sessions.items():
        try:
            expires = float(expires_at)
        except (TypeError, ValueError):
            continue
        if expires > now:
            pruned[str(key)] = expires
    return pruned


def validate_session(token: str | None) -> bool:
    if not configured():
        return False
    if not token:
        return False
    data = auth_store.read({})
    sessions = _pruned_sessions(data.get("sessions") or {})
    token_key = _token_hash(token)
    valid = token_key in sessions
    if len(sessions) != len(data.get("sessions") or {}):
        data["sessions"] = sessions
        auth_store.write(data)
    return valid


def clear_session(token: str | None) -> None:
    if not token:
        return
    data = auth_store.read({})
    sessions = data.get("sessions") or {}
    sessions.pop(_token_hash(token), None)
    data["sessions"] = sessions
    auth_store.write(data)
