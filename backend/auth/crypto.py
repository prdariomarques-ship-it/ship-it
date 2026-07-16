"""Cryptographic utilities — constant-time comparisons to prevent timing attacks."""

import hmac


def constant_time_compare(a: str, b: str) -> bool:
    """Compare two strings in constant time to prevent timing attacks.

    Uses hmac.compare_digest() which is guaranteed to use constant-time
    comparison, preventing attackers from deriving information about the
    compared values based on how long the comparison takes.
    """
    return hmac.compare_digest(a, b)
