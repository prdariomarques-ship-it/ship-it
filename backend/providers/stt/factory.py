"""Factory for speech-to-text providers -- same Factory+Strategy shape as
providers/mail/factory.py, providers/whatsapp/factory.py, etc., with one
deliberate difference: STT is OPTIONAL. Every caller
(webhooks/router.py's `_transcribe_audio`, jobs/handlers.py's owner-audio
transcription job) already treats `get_stt_provider() is None` as "no STT
backend configured -- keep existing behavior, never crash" rather than a
misconfiguration to raise on, so this returns None instead of raising
when unset, unlike the mandatory providers (mail, whatsapp, ...).

Review finding (round 6): no real STT backend is implemented here (see
base.py's module docstring for why) -- `_PROVIDERS` is deliberately empty.
`get_stt_provider()` returning None whenever `settings.stt_provider` is
unset (the default) is the correct, already-relied-upon behavior, not a
placeholder; if a real backend is ever added, it registers here the same
way GmailProvider does in providers/mail/factory.py.
"""

from providers.stt.base import STTProvider
from utils.config import get_settings

_PROVIDERS: dict[str, type[STTProvider]] = {}


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
