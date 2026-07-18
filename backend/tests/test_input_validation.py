"""Tests for input validation services — email, phone."""

from services.validation import validate_email, validate_phone_e164


class TestEmailValidation:
    def test_validate_email_accepts_valid_email(self):
        """Accepts valid email addresses."""
        assert validate_email("user@example.com") is True

    def test_validate_email_accepts_subdomain_email(self):
        """Accepts emails with subdomains."""
        assert validate_email("user@mail.example.co.uk") is True

    def test_validate_email_rejects_no_at_sign(self):
        """Rejects email without @ sign."""
        assert validate_email("userexample.com") is False

    def test_validate_email_rejects_no_domain(self):
        """Rejects email without domain."""
        assert validate_email("user@") is False

    def test_validate_email_rejects_no_local_part(self):
        """Rejects email without local part."""
        assert validate_email("@example.com") is False

    def test_validate_email_rejects_spaces(self):
        """Rejects emails with spaces."""
        assert validate_email("user @example.com") is False

    def test_validate_email_rejects_invalid_characters(self):
        """Rejects emails with invalid characters."""
        assert (
            validate_email("user+test@example.com") is True
        )  # + is valid in local part
        assert validate_email("user#@example.com") is False


class TestPhoneValidation:
    def test_validate_phone_e164_accepts_valid_format(self):
        """Accepts E.164 format phone numbers."""
        assert validate_phone_e164("+5511987654321") is True

    def test_validate_phone_e164_accepts_with_country_code(self):
        """Accepts phone with country code prefix."""
        assert validate_phone_e164("+1234567890") is True

    def test_validate_phone_e164_accepts_spaces_and_dashes(self):
        """Accepts E.164 with spaces and dashes (stripped)."""
        assert validate_phone_e164("+55 11 98765-4321") is True
        assert validate_phone_e164("+55-11-98765-4321") is True

    def test_validate_phone_e164_accepts_without_plus_prefix(self):
        """Accepts digits-only phone (the convention used by normalize_phone
        for WhatsApp-sourced numbers, and by admin-entered contacts)."""
        assert validate_phone_e164("5511999999999") is True

    def test_validate_phone_e164_rejects_starting_with_zero(self):
        """Rejects phone starting with 0 (not valid E.164), with or without '+'."""
        assert validate_phone_e164("+05511987654321") is False
        assert validate_phone_e164("05511987654321") is False

    def test_validate_phone_e164_rejects_too_short(self):
        """Rejects phone numbers too short."""
        assert validate_phone_e164("+1") is False

    def test_validate_phone_e164_rejects_too_long(self):
        """Rejects phone numbers too long (>15 digits)."""
        assert validate_phone_e164("+123456789012345678") is False

    def test_validate_phone_e164_rejects_letters(self):
        """Rejects phone with letters."""
        assert validate_phone_e164("+55119876543XX") is False

    def test_validate_phone_e164_accepts_minimal_format(self):
        """Accepts minimal valid format."""
        assert validate_phone_e164("+12") is True  # 1 = US country code, 2 digits
