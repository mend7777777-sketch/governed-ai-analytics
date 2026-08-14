"""IAM compatibility helpers; authentication models live in auth.py."""

from __future__ import annotations

from argon2 import PasswordHasher

from app.governance.auth import Principal


password_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password: str, encoded_hash: str) -> bool:
    try:
        return password_hasher.verify(encoded_hash, password)
    except Exception:
        return False


__all__ = ["Principal", "hash_password", "verify_password"]
