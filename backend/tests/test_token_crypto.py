"""Symmetric encryption for stored Gmail refresh tokens (Sprint 1)."""
from cryptography.fernet import Fernet

from services.token_crypto import TokenEncryptionNotConfigured, decrypt_token, encrypt_token
from utils.config import get_settings

import pytest


def test_encrypt_decrypt_round_trip(monkeypatch):
    monkeypatch.setattr(get_settings(), "email_token_encryption_key", Fernet.generate_key().decode())

    ciphertext = encrypt_token("a-refresh-token")
    assert ciphertext != "a-refresh-token"
    assert decrypt_token(ciphertext) == "a-refresh-token"


def test_encrypt_without_key_configured_raises(monkeypatch):
    monkeypatch.setattr(get_settings(), "email_token_encryption_key", "")
    with pytest.raises(TokenEncryptionNotConfigured):
        encrypt_token("a-refresh-token")


def test_encrypt_with_malformed_key_raises(monkeypatch):
    monkeypatch.setattr(get_settings(), "email_token_encryption_key", "not-a-valid-fernet-key")
    with pytest.raises(TokenEncryptionNotConfigured):
        encrypt_token("a-refresh-token")


def test_decrypt_with_a_different_key_than_it_was_encrypted_with_raises(monkeypatch):
    monkeypatch.setattr(get_settings(), "email_token_encryption_key", Fernet.generate_key().decode())
    ciphertext = encrypt_token("a-refresh-token")

    monkeypatch.setattr(get_settings(), "email_token_encryption_key", Fernet.generate_key().decode())
    with pytest.raises(TokenEncryptionNotConfigured):
        decrypt_token(ciphertext)


def test_decrypt_garbage_ciphertext_raises(monkeypatch):
    monkeypatch.setattr(get_settings(), "email_token_encryption_key", Fernet.generate_key().decode())
    with pytest.raises(TokenEncryptionNotConfigured):
        decrypt_token("not-a-real-ciphertext")
