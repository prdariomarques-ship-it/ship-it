"""Input validation services — SSRF, path traversal, email, phone prevention."""

import ipaddress
import re
from pathlib import Path
from urllib.parse import urlparse


def validate_url(url: str, allowed_schemes: list[str] | None = None) -> bool:
    """Whitelist validation for external URLs to prevent SSRF.

    Reject:
      - Disallowed schemes (file://, ftp://, data:, javascript:)
      - Private IP ranges (10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16, 127.0.0.0/8)
      - Reserved hostnames (localhost, 0.0.0.0, metadata.google.internal, etc.)
      - URLs with embedded credentials (http://user:pass@host/path)

    Allow: http://, https:// to public IPs and domains.

    Args:
        url: URL string to validate
        allowed_schemes: List of allowed schemes (default: ["http", "https"])

    Returns:
        True if URL is safe to use, False otherwise
    """
    if allowed_schemes is None:
        allowed_schemes = ["http", "https"]

    try:
        parsed = urlparse(url)
    except Exception:
        return False

    if parsed.scheme not in allowed_schemes:
        return False

    if parsed.username is not None or parsed.password is not None:
        return False

    hostname = parsed.hostname
    if not hostname:
        return False

    reserved_hostnames = {
        "localhost",
        "127.0.0.1",
        "0.0.0.0",
        "::1",
        "::",
        "metadata.google.internal",
        "169.254.169.254",
    }
    if hostname in reserved_hostnames:
        return False

    try:
        ip = ipaddress.ip_address(hostname)
        if ip.is_private or ip.is_loopback or ip.is_reserved or ip.is_link_local:
            return False
    except ValueError:
        pass

    return True


def validate_file_path(base_dir: str, requested_path: str) -> str:
    """Resolve file path safely within base_dir, prevent path traversal.

    Resolves `requested_path` relative to `base_dir`, ensures result stays
    within `base_dir`. Rejects paths with `..` components that escape base_dir.

    Args:
        base_dir: Base directory path (must exist)
        requested_path: Requested relative path

    Returns:
        Normalized absolute path if valid

    Raises:
        ValueError: If path escapes base_dir or is invalid
    """
    base = Path(base_dir).resolve()
    requested = Path(requested_path)

    if requested.is_absolute():
        target = requested.resolve()
    else:
        target = (base / requested).resolve()

    if not target.is_relative_to(base):
        raise ValueError(f"Path {requested_path} escapes base directory {base_dir}")

    return str(target)


def validate_email(email: str) -> bool:
    """Validate email address format (RFC 5322 subset).

    Uses a simple regex for initial validation; Pydantic's EmailStr
    provides stricter validation at schema level.

    Args:
        email: Email address to validate

    Returns:
        True if email format is valid, False otherwise
    """
    pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    return bool(re.match(pattern, email))


def validate_phone_e164(phone: str) -> bool:
    """Validate phone number in E.164 format.

    E.164 format: +[country code][number], e.g., +55 11 98765-4321 → +5511987654321

    Args:
        phone: Phone number to validate

    Returns:
        True if phone is in valid E.164 format, False otherwise
    """
    pattern = r"^\+[1-9]\d{1,14}$"
    return bool(re.match(pattern, phone.replace(" ", "").replace("-", "")))
