import hashlib
import json
import wave
from pathlib import Path

import numpy as np
import pytest

from app.config import VoiceSettings
from app.engines.fake import FakeEngine
from app.main import create_app

TOKEN_LOJA = "L" * 40
TOKEN_TWIN = "T" * 40


def write_reference(path: Path, seconds: float = 8.0, sr: int = 24000) -> None:
    """Referência SINTÉTICA de teste (tom + ruído fraco). Nenhuma voz real."""
    t = np.arange(int(seconds * sr)) / sr
    rng = np.random.default_rng(1)
    x = 0.2 * np.sin(2 * np.pi * 150 * t) + 0.01 * rng.standard_normal(t.size)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes((np.clip(x, -1, 1) * 32767).astype("<i2").tobytes())


def make_profile(profiles: Path, agent: str, *, authorized: bool = True, tamper: bool = False, text: str | None = None) -> Path:
    d = profiles / agent
    d.mkdir(parents=True)
    write_reference(d / "reference.wav")
    digest = hashlib.sha256((d / "reference.wav").read_bytes()).hexdigest()
    meta = {
        "agent": agent, "display_name": f"Voz de teste {agent}", "language": "pt", "reference_file": "reference.wav",
        "reference_sha256": ("0" * 64 if tamper else digest), "reference_text": text,
        "consent": {"authorized": authorized, "voice_owner": "Titular de teste", "scope": "teste automatizado"},
    }
    (d / "profile.json").write_text(json.dumps(meta), encoding="utf-8")
    return d


@pytest.fixture
def settings(tmp_path):
    profiles = tmp_path / "profiles"
    profiles.mkdir()
    make_profile(profiles, "loja")
    return VoiceSettings(
        tokens=f"loja={TOKEN_LOJA},twin={TOKEN_TWIN}", engine="fake", allow_fake_engine=True,
        storage_dir=tmp_path / "tmp", profiles_dir=profiles, max_text_chars=200, generation_timeout_seconds=5.0,
        max_concurrency=1, queue_max=1, result_ttl_seconds=60,
    )


@pytest.fixture
def engine():
    return FakeEngine()


@pytest.fixture
async def client(settings, engine):
    import httpx
    app = create_app(settings, engine)
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://voice") as c:
            c.app = app
            c.settings = settings
            yield c


def auth(token: str = TOKEN_LOJA) -> dict:
    return {"Authorization": f"Bearer {token}"}
