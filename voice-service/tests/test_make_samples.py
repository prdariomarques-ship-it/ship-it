"""make_samples: uma amostra por vez e várias tomadas, sem depender do psutil (importa só scripts.samples)."""
import hashlib
import json

import httpx
import pytest

from scripts import make_samples as ms

AUDIO = b"OggS-fake-audio"


def _patch_client(monkeypatch, calls):
    def handler(req: httpx.Request) -> httpx.Response:
        if req.method == "POST":
            calls.append(json.loads(req.content)["request_id"])
            return httpx.Response(200, json={"audio_id": "a1", "sha256": hashlib.sha256(AUDIO).hexdigest(), "duration_seconds": 3.0,
                                             "engine": "fake", "model_revision": "r", "reference_sha256": "0" * 64})
        if req.method == "GET":
            return httpx.Response(200, content=AUDIO)
        return httpx.Response(204)

    real = httpx.Client
    monkeypatch.setattr(ms.httpx, "Client", lambda **kw: real(transport=httpx.MockTransport(handler), **kw))


def test_only_e_takes_geram_arquivos_numerados(tmp_path, monkeypatch):
    monkeypatch.setenv("VOICE_TOKEN", "t" * 40)
    calls: list[str] = []
    _patch_client(monkeypatch, calls)
    assert ms.main(["--out", str(tmp_path), "--only", "retomada_orcamento", "--takes", "3"]) == 0
    assert sorted(p.name for p in tmp_path.glob("*.ogg")) == [f"retomada_orcamento_t{k}.ogg" for k in (1, 2, 3)]
    assert len(calls) == 3 and len(set(calls)) == 3                  # um request_id novo por tomada (sem idempotência reaproveitar)


def test_padrao_continua_uma_tomada_por_amostra(tmp_path, monkeypatch):
    monkeypatch.setenv("VOICE_TOKEN", "t" * 40)
    _patch_client(monkeypatch, [])
    assert ms.main(["--out", str(tmp_path)]) == 0
    assert sorted(p.stem for p in tmp_path.glob("*.ogg")) == sorted(ms.SAMPLES)


@pytest.mark.parametrize("n", ["0", "11"])
def test_takes_fora_da_faixa(tmp_path, monkeypatch, n):
    monkeypatch.setenv("VOICE_TOKEN", "t" * 40)
    assert ms.main(["--out", str(tmp_path), "--takes", n]) == 2
