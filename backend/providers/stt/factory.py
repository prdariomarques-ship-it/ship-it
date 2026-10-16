"""Factory for speech-to-text providers -- same Factory+Strategy shape as
providers/mail/factory.py, providers/whatsapp/factory.py, etc., with one
deliberate difference: STT is OPTIONAL. Every caller
(webhooks/router.py's `_transcribe_audio`, jobs/handlers.py's owner-audio
transcription job) already treats `get_stt_provider() is None` as "no STT
backend configured -- keep existing behavior, never crash" rather than a
misconfiguration to raise on, so this returns None instead of raising
when unset, unlike the mandatory providers (mail, whatsapp, ...).

`get_stt_provider()` returns None whenever `settings.stt_provider` is unset (the default): that is the correct, already-relied-upon
behavior, not a placeholder. The only backend registered is "groq" (providers/stt/groq.py), which stays disabled (`enabled=False`)
until GROQ_API_KEY is set.
"""

from providers.stt.base import STTProvider
from providers.stt.groq import GroqSTTProvider
from utils.config import get_settings

_PROVIDERS: dict[str, type[STTProvider]] = {"groq": GroqSTTProvider}


class UnknownSTTProviderError(ValueError):
    pass


def get_stt_provider() -> STTProvider | None:
    name = get_settings().stt_provider
    if not name:
        return None
    try:
        return _PROVIDERS[name]()
    except KeyError:
        raise UnknownSTTProviderError(
            f"Unknown STT provider {name!r}. Available: {sorted(_PROVIDERS)}"
        ) from None
