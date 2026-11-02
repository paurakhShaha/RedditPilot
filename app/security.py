"""Credential encryption helpers.

Credentials are encrypted with Fernet before they are written to SQLite and
are only decrypted inside publishing / generation services. No endpoint ever
returns a decrypted value.
"""

from __future__ import annotations

import os
import stat

from cryptography.fernet import Fernet, InvalidToken

from app.config import settings


def _load_or_create_key() -> bytes:
    if settings.secret_key:
        key = settings.secret_key.strip().encode()
        # Accept raw Fernet keys only. A hint is included in the error because
        # this runs at startup and a misconfigured key should fail loudly.
        try:
            Fernet(key)
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(
                "APP_SECRET_KEY is not a valid Fernet key. Generate one with: "
                "python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
            ) from exc
        return key

    key_file = settings.secret_key_file
    if key_file.exists():
        key = key_file.read_bytes().strip()
        try:
            Fernet(key)
            return key
        except Exception:  # noqa: BLE001
            raise RuntimeError(
                f"The local encryption key at {key_file} is invalid. Restore it or "
                "delete it (and the stored credentials) to start fresh."
            )

    key = Fernet.generate_key()
    key_file.write_bytes(key)
    try:
        os.chmod(key_file, stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass
    return key


_fernet: Fernet | None = None


def _cipher() -> Fernet:
    global _fernet
    if _fernet is None:
        _fernet = Fernet(_load_or_create_key())
    return _fernet


def encrypt_secret(value: str | None) -> str | None:
    if not value:
        return None
    return _cipher().encrypt(value.encode()).decode()


def decrypt_secret(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return _cipher().decrypt(value.encode()).decode()
    except InvalidToken as exc:
        raise ValueError(
            "Stored credential could not be decrypted. Re-enter it in Settings."
        ) from exc


def reset_cipher_for_tests() -> None:
    """Test hook used when swapping the application key."""
    global _fernet
    _fernet = None
