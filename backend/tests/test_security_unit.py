"""Unit tests for app.core.security and password strength validation."""

from datetime import timedelta

import pytest
from jose import jwt

from app.core.config import settings
from app.core.security import (
    create_access_token,
    decode_access_token,
    generate_secure_token,
    hash_password,
    hash_token,
    verify_password,
)
from app.schemas.auth import validate_password_strength


def test_hash_password_produces_verifiable_hash() -> None:
    hashed = hash_password("Str0ng!Passw0rd")
    assert hashed != "Str0ng!Passw0rd"
    assert verify_password("Str0ng!Passw0rd", hashed)


def test_verify_password_rejects_wrong_password() -> None:
    hashed = hash_password("Str0ng!Passw0rd")
    assert not verify_password("wrong-password", hashed)


def test_hash_password_is_salted_and_nondeterministic() -> None:
    assert hash_password("Str0ng!Passw0rd") != hash_password("Str0ng!Passw0rd")


def test_create_and_decode_access_token_round_trip() -> None:
    token = create_access_token({"user_id": "abc", "clinic_id": "xyz", "role": "THERAPIST"})
    payload = decode_access_token(token)
    assert payload is not None
    assert payload["user_id"] == "abc"
    assert payload["role"] == "THERAPIST"
    assert payload["type"] == "access"


def test_decode_access_token_rejects_expired_token() -> None:
    token = create_access_token({"user_id": "abc"}, expires_delta=timedelta(seconds=-1))
    assert decode_access_token(token) is None


def test_decode_access_token_rejects_bad_signature() -> None:
    token = jwt.encode({"user_id": "abc", "type": "access"}, "wrong-secret", algorithm=settings.JWT_ALGORITHM)
    assert decode_access_token(token) is None


def test_decode_access_token_rejects_non_access_type() -> None:
    token = jwt.encode({"user_id": "abc", "type": "refresh"}, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    assert decode_access_token(token) is None


def test_generate_secure_token_is_unique_and_high_entropy() -> None:
    tokens = {generate_secure_token() for _ in range(50)}
    assert len(tokens) == 50
    assert all(len(t) >= 32 for t in tokens)


def test_hash_token_is_deterministic() -> None:
    token = generate_secure_token()
    assert hash_token(token) == hash_token(token)


def test_hash_token_differs_for_different_tokens() -> None:
    assert hash_token(generate_secure_token()) != hash_token(generate_secure_token())


@pytest.mark.parametrize(
    "password",
    [
        "short1!A",  # too short
        "alllowercase123!",  # no uppercase
        "ALLUPPERCASE123!",  # no lowercase
        "NoDigitsHere!!!!",  # no digit
        "NoSpecialChar123",  # no special char
    ],
)
def test_password_strength_rejects_weak_passwords(password: str) -> None:
    with pytest.raises(ValueError):
        validate_password_strength(password)


def test_password_strength_accepts_strong_password() -> None:
    assert validate_password_strength("Str0ng!Passw0rd") == "Str0ng!Passw0rd"
