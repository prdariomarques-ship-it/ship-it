"""Motor `elevenlabs` com httpx.MockTransport: nenhuma chamada de rede real, nenhuma chave real."""
import json
from pathlib import Path

import httpx
import numpy as np
import pytest
from pydantic import ValidationError

from app.config import VoiceSettings
from app.engines import build_engine
from app.engines.base import EngineError, EngineNotReady
from app.engines.elevenlabs_engine import ElevenLabsEngine

VOICE = "AbCdEfGhIjKl1234"
KEY = "sk_test_chave_ficticia_123"


def _settings(tmp_path, **kw):
    key_file = tmp_path / "k.txt"
    key_file.write_text(KEY + "\n", encoding="utf-8")
    base = dict(tokens="loja=" + "L" * 40, engine="elevenlabs", elevenlabs_voice_id=VOICE, elevenlabs_api_key_file=key_file)
    base.update(kw)
    return VoiceSettings(**base)


def _pcm(n=4800):
    return (np.sin(np.arange(n) / 10) * 12000).astype("<i2").tobytes()


def _engine(tmp_path, handler, **kw):
    s = _settings(tmp_path, **kw)
    eng = ElevenLabsEngine(s, client=httpx.Client(base_url=s.elevenlabs_base_url, transport=httpx.MockTransport(handler)), sleep=lambda _s: None)
    eng.load()
    return eng


def _call(eng):
    return eng.synthesize("Olá, tudo bem?", "pt", Path("ignorada.wav"), None)


def test_registered_and_identity(tmp_path):
    assert isinstance(build_engine(_settings(tmp_path)), ElevenLabsEngine)
    eng = ElevenLabsEngine(_settings(tmp_path))
    assert eng.name == "elevenlabs" and eng.model_revision == VOICE and eng.model_id.endswith("eleven_multilingual_v2")


def test_request_shape_and_decode(tmp_path):
    seen = {}

    def handler(req):
        seen.update(path=req.url.path, query=dict(req.url.params), key=req.headers.get("xi-api-key"), body=json.loads(req.content))
        return httpx.Response(200, content=_pcm())

    res = _call(_engine(tmp_path, handler))
    assert seen["path"] == f"/v1/text-to-speech/{VOICE}" and seen["query"] == {"output_format": "pcm_24000"} and seen["key"] == KEY
    b = seen["body"]
    assert b["text"] == "Olá, tudo bem?" and b["model_id"] == "eleven_multilingual_v2"
    assert set(b["voice_settings"]) == {"stability", "similarity_boost", "style", "use_speaker_boost", "speed"}
    assert "language_code" not in b  # multilingual_v2 não aceita o campo
    assert res.sample_rate == 24000 and res.samples.dtype == np.float32 and res.samples.shape == (4800,)
    assert np.max(np.abs(res.samples)) <= 1.0


def test_language_code_only_for_models_that_accept_it(tmp_path):
    bodies = []

    def handler(req):
        bodies.append(json.loads(req.content))
        return httpx.Response(200, content=_pcm())

    _call(_engine(tmp_path, handler, elevenlabs_model_id="eleven_flash_v2_5"))
    assert bodies[0]["language_code"] == "pt"


def test_odd_byte_count_is_trimmed(tmp_path):
    assert _call(_engine(tmp_path, lambda r: httpx.Response(200, content=_pcm(100) + b"\x01"))).samples.shape == (100,)


def test_retries_then_succeeds_on_429(tmp_path):
    codes = iter([429, 503, 200])

    def handler(req):
        c = next(codes)
        return httpx.Response(c, content=_pcm() if c == 200 else b"busy")

    assert _call(_engine(tmp_path, handler)).samples.size == 4800


def test_gives_up_after_retries(tmp_path):
    calls = []

    def handler(req):
        calls.append(1)
        return httpx.Response(500, text="boom")

    with pytest.raises(EngineError, match="indisponível"):
        _call(_engine(tmp_path, handler, elevenlabs_max_retries=1))
    assert len(calls) == 2


def test_timeout_is_retried_and_reported(tmp_path):
    def handler(req):
        raise httpx.ReadTimeout("t", request=req)

    with pytest.raises(EngineError, match="tempo esgotado"):
        _call(_engine(tmp_path, handler, elevenlabs_max_retries=1))


@pytest.mark.parametrize("status,msg", [(401, "chave"), (403, "chave"), (402, "créditos"), (422, "recusou a requisição")])
def test_no_retry_on_client_errors(tmp_path, status, msg):
    calls = []

    def handler(req):
        calls.append(1)
        return httpx.Response(status, json={"detail": {"status": "x"}})

    with pytest.raises(EngineError, match=msg):
        _call(_engine(tmp_path, handler))
    assert len(calls) == 1


def test_error_never_leaks_key(tmp_path):
    def handler(req):
        return httpx.Response(401, text=f"eco da chave: {req.headers['xi-api-key']}")

    with pytest.raises(EngineError) as ei:
        _call(_engine(tmp_path, handler))
    assert KEY not in str(ei.value)


def test_empty_audio_is_error(tmp_path):
    with pytest.raises(EngineError, match="vazio"):
        _call(_engine(tmp_path, lambda r: httpx.Response(200, content=b"")))


def test_load_requires_voice_and_key(tmp_path):
    with pytest.raises(EngineNotReady, match="VOICE_ID"):
        ElevenLabsEngine(_settings(tmp_path, elevenlabs_voice_id="")).load()
    with pytest.raises(EngineNotReady, match="chave"):
        ElevenLabsEngine(VoiceSettings(tokens="loja=" + "L" * 40, engine="elevenlabs", elevenlabs_voice_id=VOICE)).load()
    with pytest.raises(EngineNotReady, match="API_KEY_FILE"):
        ElevenLabsEngine(_settings(tmp_path, elevenlabs_api_key_file=tmp_path / "nao_existe.txt")).load()


def test_key_from_env_style_secret(tmp_path):
    s = VoiceSettings(tokens="loja=" + "L" * 40, engine="elevenlabs", elevenlabs_voice_id=VOICE, elevenlabs_api_key=KEY)
    assert KEY not in repr(s)  # SecretStr
    seen = {}
    eng = ElevenLabsEngine(s, client=httpx.Client(base_url=s.elevenlabs_base_url, transport=httpx.MockTransport(
        lambda r: seen.setdefault("k", r.headers["xi-api-key"]) and httpx.Response(200, content=_pcm()))))
    eng.load()
    _call(eng)
    assert seen["k"] == KEY


def test_settings_ranges(tmp_path):
    for kw in ({"elevenlabs_stability": 1.5}, {"elevenlabs_speed": 2.0}, {"elevenlabs_max_retries": 9}):
        with pytest.raises(ValidationError):
            VoiceSettings(**kw)
