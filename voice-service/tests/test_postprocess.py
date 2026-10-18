"""Pós-processamento do áudio gerado: desligado = identidade; pausas/ritmo/brilho fazem o que dizem; o serviço só o aplica quando ligado."""
import numpy as np
import pytest
from pydantic import ValidationError

from app import audio
from app.config import VoiceSettings
from app.main import create_app
from app.postprocess import compact_pauses, postprocess
from tests.conftest import TOKEN_LOJA

SR = 24000


def voiced(seconds: float, seed: int = 1) -> np.ndarray:
    rng = np.random.default_rng(seed)
    t = np.arange(int(seconds * SR)) / SR
    return (0.4 * np.sin(2 * np.pi * 180 * t) * (0.6 + 0.4 * rng.random(t.size))).astype(np.float32)


def gap(seconds: float) -> np.ndarray:
    return np.zeros(int(seconds * SR), dtype=np.float32)


def high_share(x: np.ndarray) -> float:
    spec = np.abs(np.fft.rfft(x * np.hanning(len(x)))) ** 2
    f = np.fft.rfftfreq(len(x), 1 / SR)
    return float(spec[f > 4000].sum() / spec.sum())


def test_desligado_devolve_o_mesmo_objeto():
    x = voiced(1.0)
    assert postprocess(x, SR) is x


def test_pausa_longa_encolhe_e_a_fala_fica_identica():
    a, b = voiced(1.0, 1), voiced(1.0, 2)
    y = compact_pauses(np.concatenate([a, gap(2.0), b]), SR)
    assert len(y) == pytest.approx(len(a) + len(b) + 0.24 * SR, abs=0.03 * SR)
    assert np.array_equal(y[: len(a)], a) and np.array_equal(y[-len(b):], b)


def test_pausa_curta_nao_e_tocada():
    x = np.concatenate([voiced(1.0, 1), gap(0.28), voiced(1.0, 2)])
    assert len(compact_pauses(x, SR)) >= len(x) - int(0.02 * SR)


def test_silencio_total_nao_quebra():
    assert len(compact_pauses(gap(1.0), SR)) == SR


def test_tempo_encurta_sem_mudar_o_tom():
    x = voiced(2.0)
    y = postprocess(x, SR, tempo=1.25)
    assert len(y) == pytest.approx(len(x) / 1.25, rel=0.03)
    f = np.fft.rfftfreq(len(y), 1 / SR)
    assert abs(f[np.argmax(np.abs(np.fft.rfft(y)))] - 180) < 6      # mesma frequência fundamental


def test_brilho_aumenta_energia_acima_de_4khz():
    rng = np.random.default_rng(3)
    t = np.arange(2 * SR) / SR
    x = (0.4 * np.sin(2 * np.pi * 180 * t) + 0.02 * rng.standard_normal(t.size)).astype(np.float32)   # voz abafada: quase tudo grave
    assert high_share(postprocess(x, SR, brightness_db=3.0)) > 1.5 * high_share(x)


def test_combinado_devolve_float32_mono_finito():
    x = np.concatenate([voiced(1.0, 1), gap(1.5), voiced(1.0, 2)])
    y = postprocess(x, SR, compact=True, tempo=1.12, brightness_db=3.0)
    assert y.dtype == np.float32 and y.ndim == 1 and np.all(np.isfinite(y)) and len(y) < len(x) * 0.7


@pytest.mark.parametrize("field,value", [("post_tempo", 0.5), ("post_tempo", 2.0), ("post_brightness_db", -1.0), ("post_brightness_db", 9.0)])
def test_faixa_dos_parametros(field, value):
    with pytest.raises(ValidationError, match=field):
        VoiceSettings(tokens="loja=" + "a" * 40, **{field: value})


def test_padroes_do_servico_sao_desligados():
    s = VoiceSettings(tokens="loja=" + "a" * 40)
    assert (s.post_compact_pauses, s.post_tempo, s.post_brightness_db) == (False, 1.0, 0.0)


async def _duracao(settings, engine, rid):
    import httpx
    app = create_app(settings, engine)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://v") as c:
            h = {"Authorization": f"Bearer {TOKEN_LOJA}"}
            r = await c.post("/v1/synthesize", json={"request_id": rid, "text": "Olá, tudo bem?", "language": "pt"}, headers=h)
            assert r.status_code == 200, r.text
            a = await c.get(f"/v1/audio/{r.json()['audio_id']}", headers=h)
            return audio.probe_ogg_opus(a.content).duration_seconds


async def test_servico_aplica_o_ritmo_quando_ligado(settings, engine):
    base = await _duracao(settings, engine, "req-pp-000001")
    settings.post_tempo = 1.25
    rapido = await _duracao(settings, engine, "req-pp-000002")
    assert rapido == pytest.approx(base / 1.25, rel=0.08)
