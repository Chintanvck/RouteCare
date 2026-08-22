"""
RouteCare AI - Security primitives.

Password hashing, opaque token generation, and JWT helpers.

Password hashing uses the `bcrypt` library directly rather than
passlib: passlib 1.7.4 (last released 2020) is incompatible with
bcrypt>=4.1 (it probes a `bcrypt.__about__` attribute that no longer
exists), so it fails on every hash/verify call in this environment.
bcrypt's own API is small enough that passlib's abstraction isn't
needed here.
"""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
from jose import JWTError, jwt

from app.core.config import settings

# bcrypt only considers the first 72 bytes of the input; anything past
# that is silently ignored. Schemas enforce a max password length of 72
# characters so hashing never truncates unexpectedly.
_BCRYPT_ROUNDS = 12


def hash_password(plain_password: str) -> str:
    """Hash a plaintext password using bcrypt."""
    salt = bcrypt.gensalt(rounds=_BCRYPT_ROUNDS)
    return bcrypt.hashpw(plain_password.encode("utf-8"), salt).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plaintext password against a bcrypt hash."""
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
    except ValueError:
        # Malformed hash (shouldn't happen for hashes we generated ourselves).
        return False


def generate_secure_token(n_bytes: int = 32) -> str:
    """Generate a high-entropy opaque token for refresh/password-reset use."""
    return secrets.token_urlsafe(n_bytes)


def hash_token(raw_token: str) -> str:
    """
    Hash an opaque token (refresh token, password reset token) for storage.

    SHA-256 (not bcrypt) is intentional: these tokens are already
    high-entropy random strings, not human-chosen passwords, so a fast
    deterministic hash keyed on the token itself is sufficient and lets
    us look the token up by its hash in a single indexed query.
    """
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def create_access_token(data: dict[str, Any], expires_delta: timedelta | None = None) -> str:
    """
    Create a signed JWT access token.

    Expected claims (per Security & Compliance doc): user_id, clinic_id, role, exp.
    """
    to_encode = data.copy()
    now = datetime.now(timezone.utc)
    expire = now + (expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode["iat"] = now
    to_encode["exp"] = expire
    to_encode["type"] = "access"
    to_encode["jti"] = secrets.token_hex(16)
    return jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any] | None:
    """Decode and validate a JWT access token. Returns None if invalid/expired/wrong type."""
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except JWTError:
        return None
    if payload.get("type") != "access":
        return None
    return payload
