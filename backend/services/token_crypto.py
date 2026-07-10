"""Symmetric encryption for credentials at rest — today, only Gmail refresh
tokens (`models.email_account.EmailAccount.encrypted_refresh_token`).

"Nenhuma credencial poderá ser persistida em texto puro" (Sprint 1 — Gmail):
a refresh token is a long-lived bearer credential for someone's mailbox: a
password-hash-style one-way check doesn't apply here (the app must present
the *actual* token to Google to refresh access), so this uses symmetric
encryption (Fernet — AES-128-CBC + HMAC, authenticated) with a key that
never leaves configuration, never touches the database.
"""
from cryptography.fernet import Fernet, InvalidToken

from utils.config import get_settings


class TokenEncryptionNotConfigured(RuntimeError):
    """EMAIL_TOKEN_ENCRYPTION_KEY is unset — refuse to store/read a token
    rather than ever fall back to plaintext."""


def _fernet() -> Fernet:
    key = get_settings().email_token_encryption_key
    if not key:
        raise TokenEncryptionNotConfigured(
            "EMAIL_TOKEN_ENCRYPTION_KEY is not configured — generate one with: "
            "python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
        )
    try:
        return Fernet(key.encode())
    except (ValueError, TypeError) as exc:
        raise TokenEncryptionNotConfigured(
            "EMAIL_TOKEN_ENCRYPTION_KEY is not a valid Fernet key (32 url-safe base64-encoded bytes)"
        ) from exc


def encrypt_token(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt_token(ciphertext: str) -> str:
    try:
        return _fernet().decrypt(ciphertext.encode()).decode()
    except InvalidToken as exc:
        raise TokenEncryptionNotConfigured(
            "Stored token could not be decrypted — EMAIL_TOKEN_ENCRYPTION_KEY changed or is wrong"
        ) from exc
