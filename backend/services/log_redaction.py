"""Log redaction filter — mask sensitive fields to prevent data leakage."""

import copy
import logging
from typing import Any


class LogRedactionFilter(logging.Filter):
    """Filter that redacts sensitive fields from log records.

    Sensitive fields redacted:
      - password, passwd, pwd
      - token, access_token, refresh_token, api_key, secret, api_secret
      - credit_card, ccn, card_number
      - ssn, social_security_number
      - pii (if explicitly tagged)
    """

    SENSITIVE_KEYS = {
        "password",
        "passwd",
        "pwd",
        "token",
        "access_token",
        "refresh_token",
        "api_key",
        "api_secret",
        "secret",
        "credit_card",
        "ccn",
        "card_number",
        "ssn",
        "social_security_number",
        "pii",
    }

    def filter(self, record: logging.LogRecord) -> bool:
        if hasattr(record, "context") and isinstance(record.context, dict):
            record.context = self._redact_dict(record.context)
        if hasattr(record, "msg") and isinstance(record.msg, dict):
            record.msg = self._redact_dict(record.msg)
        return True

    def _redact_dict(self, data: dict) -> dict:
        """Recursively redact sensitive keys in a dictionary."""
        if not data:
            return data

        result = copy.deepcopy(data)
        self._redact_recursive(result)
        return result

    def _redact_recursive(self, obj: Any) -> None:
        """Recursively redact sensitive values in nested structures."""
        if isinstance(obj, dict):
            for key, value in obj.items():
                if key.lower() in self.SENSITIVE_KEYS:
                    obj[key] = "***REDACTED***"
                elif isinstance(value, (dict, list)):
                    self._redact_recursive(value)
        elif isinstance(obj, list):
            for item in obj:
                if isinstance(item, (dict, list)):
                    self._redact_recursive(item)
