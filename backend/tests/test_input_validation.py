"""Tests for input validation services — SSRF, path traversal, email, phone."""
import pytest
import tempfile

from services.validation import (
    validate_url,
    validate_file_path,
    validate_email,
    validate_phone_e164,
)


class TestUrlValidation:
    def test_validate_url_accepts_http(self):
        """Accepts HTTP URLs."""
        assert validate_url("http://example.com") is True

    def test_validate_url_accepts_https(self):
        """Accepts HTTPS URLs."""
        assert validate_url("https://example.com") is True

    def test_validate_url_rejects_file_scheme(self):
        """Rejects file:// scheme."""
        assert validate_url("file:///etc/passwd") is False

    def test_validate_url_rejects_ftp_scheme(self):
        """Rejects ftp:// scheme."""
        assert validate_url("ftp://example.com") is False

    def test_validate_url_rejects_data_scheme(self):
        """Rejects data: scheme."""
        assert validate_url("data:text/html,<script>alert(1)</script>") is False

    def test_validate_url_rejects_javascript_scheme(self):
        """Rejects javascript: scheme."""
        assert validate_url("javascript:alert(1)") is False

    def test_validate_url_rejects_loopback_127(self):
        """Rejects 127.0.0.1 (loopback)."""
        assert validate_url("http://127.0.0.1:6379") is False

    def test_validate_url_rejects_private_range_10(self):
        """Rejects 10.x.x.x private range."""
        assert validate_url("http://10.0.0.1") is False

    def test_validate_url_rejects_private_range_172(self):
        """Rejects 172.16.0.0/12 private range."""
        assert validate_url("http://172.16.0.1") is False

    def test_validate_url_rejects_private_range_192(self):
        """Rejects 192.168.x.x private range."""
        assert validate_url("http://192.168.1.1") is False

    def test_validate_url_rejects_localhost_hostname(self):
        """Rejects localhost hostname."""
        assert validate_url("http://localhost") is False

    def test_validate_url_rejects_metadata_google_internal(self):
        """Rejects metadata.google.internal."""
        assert validate_url("http://metadata.google.internal") is False

    def test_validate_url_rejects_embedded_credentials(self):
        """Rejects URLs with embedded username/password."""
        assert validate_url("http://user:password@example.com") is False

    def test_validate_url_accepts_public_domain(self):
        """Accepts public domain URLs."""
        assert validate_url("https://api.github.com/repos") is True

    def test_validate_url_accepts_public_ip(self):
        """Accepts public IP addresses."""
        assert validate_url("https://8.8.8.8") is True

    def test_validate_url_invalid_url(self):
        """Handles invalid URLs gracefully."""
        assert validate_url("not a url") is False


class TestFilePathValidation:
    def test_validate_file_path_accepts_relative_path(self):
        """Accepts relative paths within base directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = validate_file_path(tmpdir, "file.txt")
            assert result.startswith(tmpdir)
            assert "file.txt" in result

    def test_validate_file_path_accepts_nested_path(self):
        """Accepts nested relative paths."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = validate_file_path(tmpdir, "subdir/file.txt")
            assert result.startswith(tmpdir)
            assert "subdir" in result

    def test_validate_file_path_rejects_traversal_attempt(self):
        """Rejects paths with .. traversal."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with pytest.raises(ValueError, match="escapes base directory"):
                validate_file_path(tmpdir, "../etc/passwd")

    def test_validate_file_path_rejects_traversal_from_subdirectory(self):
        """Rejects .. traversal from nested paths."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with pytest.raises(ValueError, match="escapes base directory"):
                validate_file_path(tmpdir, "subdir/../../etc/passwd")

    def test_validate_file_path_handles_dot_segments(self):
        """Handles . and .. correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = validate_file_path(tmpdir, "subdir/./file.txt")
            assert result.startswith(tmpdir)

    def test_validate_file_path_rejects_absolute_path_escape(self):
        """Rejects absolute paths that escape base directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with pytest.raises(ValueError, match="escapes base directory"):
                validate_file_path(tmpdir, "/etc/passwd")


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
        assert validate_email("user+test@example.com") is True  # + is valid in local part
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

    def test_validate_phone_e164_rejects_without_country_code(self):
        """Rejects phone without country code."""
        assert validate_phone_e164("1234567890") is False

    def test_validate_phone_e164_rejects_starting_with_zero(self):
        """Rejects phone starting with 0 (not valid E.164)."""
        assert validate_phone_e164("+05511987654321") is False

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
