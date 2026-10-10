"""Provider-agnostic speech-to-text contract (Strategy pattern) -- same
shape as providers/mail/base.py, providers/whatsapp/base.py, etc.

CI/review finding (round 6, "reconciliar a base"): webhooks/router.py and
jobs/handlers.py both import `STTProviderError` from here and
`get_stt_provider` from providers/stt/factory.py, and both have real
behavior that depends on `get_stt_provider() is None` meaning "no STT
backend configured" (see router.py's `_transcribe_audio`: "no STT
provider configured... all just mean the message keeps its pre-existing
behaviour (empty text, no auto-reply)"). Neither this file nor the
factory existed anywhere in this repository -- the whole package was
missing, which made `backend/tests/` (via main.py -> webhooks.router)
fail to even import, blocking collection of the main test suite entirely.

This is the real, minimal CONTRACT those call sites already assume --
not a test-only stub. What it deliberately does NOT do: implement an
actual transcription backend (Whisper API, Google STT, a local model,
etc.). There is no evidence anywhere in this repository or this review's
VPS-sourced findings of which backend production actually uses, if any
-- `get_stt_provider()` (providers/stt/factory.py) returns None by
default for exactly this reason, which is already the correct, intended
behavior per the calling code above, not a workaround. Wiring a real
backend requires: the real `stt_provider` setting value production uses
(if any), its credentials/base URL, and its actual request/response
shape -- none of that is available here; implementing one would be
guessing at content this review has no basis for.
"""

from abc import ABC, abstractmethod


class STTProviderError(RuntimeError):
    pass


class STTProvider(ABC):
    """Strategy interface for a speech-to-text backend.

    `enabled` lets a configured-but-not-ready provider (e.g. missing API
    key) report itself as unavailable without the caller needing to know
    why -- router.py's `_transcribe_audio` treats `not stt.enabled` the
    same as `stt is None`: skip transcription, keep existing behavior.
    """

    name: str

    @property
    @abstractmethod
    def enabled(self) -> bool: ...

    @abstractmethod
    async def transcribe(self, audio_bytes: bytes, mime_type: str) -> str:
        """Return the transcribed text, or raise `STTProviderError` on any
        failure (unsupported format, backend error, empty result) -- never
        return a guessed/partial transcript silently."""
