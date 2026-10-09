"""FAKE rate_limiter -- always allows, not exercised by send_whatsapp_text
(only by twin_autopilot_check, which this test file does not call)."""


class _FakeRateLimiter:
    async def is_allowed(self, key, limit, window_seconds):
        return True


rate_limiter = _FakeRateLimiter()
