"""Input validation services — email and phone format checks."""

import re


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
    """Validate phone number as E.164 digits, leading '+' optional.

    E.164 shape: [country code][number], e.g. +55 11 98765-4321 -> 5511987654321.
    The leading '+' is accepted but not required: WhatsApp-sourced numbers
    reach this codebase already stripped of it (see
    providers/whatsapp/base.py::normalize_phone), so both '+5511987654321'
    and '5511987654321' are valid.

    Args:
        phone: Phone number to validate

    Returns:
        True if phone is in valid E.164 format, False otherwise
    """
    digits = phone.replace(" ", "").replace("-", "").removeprefix("+")
    pattern = r"^[1-9]\d{1,14}$"
    return bool(re.match(pattern, digits))
