import asyncio
import os
import stat
import time

import numpy as np
import pytest

from app import audio
from app.engines.base import EngineError
from tests.conftest import TOKEN_TWIN, auth, make_profile

TEXT = "Olá! Aqui é o assistente da loja. Seu orçamento está pronto."


def body(rid="req-00000001", text=TEXT, lang="pt"):
    return {"request_id": rid, "text": text, "language": lang}


async def test_healthz_publico_sem_detalhes(client):
    r = await client.get("/healthz")
    assert r.status_code == 200 and r.json() == {"status": "ok"}


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer errado"}, {"Authorization": "Basic abc"}, {"Authorization": ""}])
async def test_sem_token_valido_nega(client, headers):
    for method, url in (("get", "/readyz"), ("post", "/v1/synthesize")):
        r = await getattr(client, method)(url, headers=headers, **({"json": body()} if method == "post" else {}))
        assert r.status_code == 401, (url, r.text)
    assert (await client.get("/v1/audio/abc", headers=headers)).status_code == 401


async def test_documentacao_nao_exposta(client):
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert (await client.get(path)).status_code == 404


async def test_sintese_valida_ogg_opus_mono(client, engine):
    r = await client.post("/v1/synthesize", json=body(), headers=auth())
    assert r.status_code == 200, r.text
    meta = r.json()
    assert meta["mime"] == "audio/ogg; codecs=opus" and meta["synthetic_voice"] is True and meta["profile"] == "loja"
    a = await client.get(f"/v1/audio/{meta['audio_id']}", headers=auth())
    assert a.status_code == 200 and a.headers["content-type"].startswith("audio/ogg") and a.headers["cache-control"] == "no-store"
    import hashlib
    assert hashlib.sha256(a.content).hexdigest() == meta["sha256"] == a.headers["x-audio-sha256"]
    info = audio.probe_ogg_opus(a.content)
    assert (info.codec, info.channels) == ("opus", 1) and 0.5 < info.duration_seconds < 40
    assert abs(info.duration_seconds - meta["duration_seconds"]) < 0.1
    assert info.peak_dbfs <= -2.5          # pico limitado, sem clipping


async def test_perfil_e_por_agente_token_de_outro_agente_nao_usa_nem_le(client):
    # 'twin' não tem perfil -> não consegue sintetizar com a voz da loja
    r = await client.post("/v1/synthesize", json=body(), headers=auth(TOKEN_TWIN))
    assert r.status_code == 404 and r.json()["error"]["code"] == "profile_unavailable"
    meta = (await client.post("/v1/synthesize", json=body(), headers=auth())).json()
    assert (await client.get(f"/v1/audio/{meta['audio_id']}", headers=auth(TOKEN_TWIN))).status_code == 404
    assert (await client.delete(f"/v1/audio/{meta['audio_id']}", headers=auth(TOKEN_TWIN))).status_code == 404


@pytest.mark.parametrize("payload, status, code", [
    (body(text="   "), 400, "empty_text"),
    (body(text="x" * 201), 413, "text_too_long"),
    (body(lang="en"), 400, "unsupported_language"),
    (body(rid="curto"), 422, None),           # rejeitado já pelo esquema
    (body(rid="com espaco no id"), 400, "invalid_request_id"),
])
async def test_entradas_invalidas(client, payload, status, code):
    r = await client.post("/v1/synthesize", json=payload, headers=auth())
    assert r.status_code == status, r.text
    if code:
        assert r.json()["error"]["code"] == code


async def test_corpo_grande_demais(client):
    r = await client.post("/v1/synthesize", content=b"x" * 9000, headers={**auth(), "content-type": "application/json"})
    assert r.status_code == 413


async def test_idempotencia_mesmo_request_id_gera_uma_vez(client, engine):
    a = (await client.post("/v1/synthesize", json=body("req-idem-001"), headers=auth())).json()
    b = (await client.post("/v1/synthesize", json=body("req-idem-001"), headers=auth())).json()
    assert a["audio_id"] == b["audio_id"] and len(engine.calls) == 1


async def test_concorrentes_com_mesmo_request_id_compartilham_uma_geracao(client, engine):
    engine.delay = 0.3
    rs = await asyncio.gather(*[client.post("/v1/synthesize", json=body("req-same-0001"), headers=auth()) for _ in range(3)])
    assert [r.status_code for r in rs] == [200, 200, 200] and len(engine.calls) == 1
    assert len({r.json()["audio_id"] for r in rs}) == 1


async def test_falha_do_motor(client, engine):
    engine.fail_with = EngineError("CUDA out of memory")
    r = await client.post("/v1/synthesize", json=body("req-fail-001"), headers=auth())
    assert r.status_code == 500 and r.json()["error"]["code"] == "engine_failure"
    engine.fail_with = None                     # falha não fica gravada: nova tentativa funciona
    assert (await client.post("/v1/synthesize", json=body("req-fail-001"), headers=auth())).status_code == 200


async def test_audio_longo_demais_e_recusado(client, engine):
    engine.seconds_per_char = 0.5                # ~ 30 chars -> 15s ok; texto de 100 chars -> 50s > 40s
    ok = await client.post("/v1/synthesize", json=body("req-long-001", text="a" * 60), headers=auth())
    assert ok.status_code == 200
    r = await client.post("/v1/synthesize", json=body("req-long-002", text="a" * 100), headers=auth())
    assert r.status_code == 422 and r.json()["error"]["code"] == "audio_too_long"


async def test_audio_invalido_nan_e_recusado(client, engine):
    from app.engines.base import SynthesisResult
    engine.synthesize = lambda *a, **k: SynthesisResult(np.full(24000, np.nan, dtype=np.float32), 24000)
    r = await client.post("/v1/synthesize", json=body("req-nan-0001"), headers=auth())
    assert r.status_code == 502 and r.json()["error"]["code"] == "invalid_audio_format"


async def test_audio_curto_demais(client, engine):
    from app.engines.base import SynthesisResult
    engine.synthesize = lambda *a, **k: SynthesisResult(np.zeros(100, dtype=np.float32), 24000)
    r = await client.post("/v1/synthesize", json=body("req-short-01"), headers=auth())
    assert r.status_code == 422 and r.json()["error"]["code"] == "audio_too_short"


async def test_fila_cheia_devolve_429_e_nunca_roda_alem_da_concorrencia(client, engine):
    # max_concurrency=1, queue_max=1 -> 2 admitidos; o 3º leva 429
    running = {"now": 0, "max": 0}
    original = engine.synthesize

    def tracked(*a, **k):
        running["now"] += 1
        running["max"] = max(running["max"], running["now"])
        try:
            return original(*a, **k)
        finally:
            running["now"] -= 1
    engine.synthesize = tracked
    engine.delay = 0.4
    rs = await asyncio.gather(*[client.post("/v1/synthesize", json=body(f"req-q-00000{i}"), headers=auth()) for i in range(3)])
    codes = sorted(r.status_code for r in rs)
    assert codes == [200, 200, 429], codes
    assert running["max"] == 1                 # nunca duas sínteses simultâneas


async def test_timeout_nao_libera_capacidade_enquanto_o_thread_roda(settings, engine):
    import httpx
    from app.main import create_app
    settings.generation_timeout_seconds = 0.2
    settings.queue_max = 0
    app = create_app(settings, engine)
    engine.delay = 0.8
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://v") as c:
            r1 = await c.post("/v1/synthesize", json=body("req-to-000001"), headers=auth())
            assert r1.status_code == 504 and r1.json()["error"]["code"] == "generation_timeout"
            r2 = await c.post("/v1/synthesize", json=body("req-to-000002"), headers=auth())
            assert r2.status_code == 429            # o thread da 1ª ainda ocupa a vaga
            await asyncio.sleep(1.0)                # o thread termina
            settings.generation_timeout_seconds = 5
            r3 = await c.post("/v1/synthesize", json=body("req-to-000001"), headers=auth())
            assert r3.status_code == 200            # repetição do mesmo id aproveita o resultado que terminou
            assert len(engine.calls) == 1


async def test_armazenamento_privado_limpeza_e_delete(client, settings):
    meta = (await client.post("/v1/synthesize", json=body("req-st-000001"), headers=auth())).json()
    d = settings.storage_dir
    assert stat.S_IMODE(os.stat(d).st_mode) == 0o700
    files = list(d.glob("*.ogg"))
    assert len(files) == 1 and stat.S_IMODE(os.stat(files[0]).st_mode) == 0o600
    assert (await client.delete(f"/v1/audio/{meta['audio_id']}", headers=auth())).status_code == 204
    assert not list(d.glob("*.ogg"))
    assert (await client.get(f"/v1/audio/{meta['audio_id']}", headers=auth())).status_code == 404


async def test_ttl_remove_arquivo_e_resultado(client, settings):
    service = client.app.state.service
    meta = (await client.post("/v1/synthesize", json=body("req-ttl-00001"), headers=auth())).json()
    assert list(settings.storage_dir.glob("*.ogg"))
    for key in list(service._done):
        a, exp, fp = service._done[key]
        service._done[key] = (a, time.time() - 1, fp)
    for it in service.store._items.values():
        it.created = time.time() - 10_000
    assert service.sweep() == 1
    assert not list(settings.storage_dir.glob("*.ogg"))
    assert (await client.get(f"/v1/audio/{meta['audio_id']}", headers=auth())).status_code == 404


def test_sobras_de_execucao_anterior_sao_apagadas_na_subida(settings, engine):
    from app.main import create_app
    settings.storage_dir.mkdir(parents=True)
    (settings.storage_dir / "velho.ogg").write_bytes(b"OggS")
    create_app(settings, engine)
    assert not list(settings.storage_dir.glob("*.ogg"))


async def test_perfil_sem_consentimento_ou_adulterado_e_recusado(settings, engine, tmp_path):
    import httpx
    from app.main import create_app
    make_profile(settings.profiles_dir, "twin", authorized=False)
    make_profile(settings.profiles_dir, "adulterado", tamper=True)
    settings.tokens += ",adulterado=" + "A" * 40
    app = create_app(settings, engine)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://v") as c:
            for token in (TOKEN_TWIN, "A" * 40):
                r = await c.post("/v1/synthesize", json=body(), headers=auth(token))
                assert r.status_code == 404 and r.json()["error"]["code"] == "profile_unavailable"


async def test_readyz_lista_so_o_perfil_do_proprio_agente(client):
    r = await client.get("/readyz", headers=auth())
    j = r.json()
    assert j["ready"] is True and j["profiles"] == ["loja"] and j["engine"] == "fake" and j["max_concurrency"] == 1
    j2 = (await client.get("/readyz", headers=auth(TOKEN_TWIN))).json()
    assert j2["profiles"] == []


def test_motor_fake_e_recusado_sem_flag(settings):
    from app.engines.base import EngineNotReady, build_engine
    settings.allow_fake_engine = False
    with pytest.raises(EngineNotReady):
        build_engine(settings)


def test_tokens_curtos_ou_ausentes_impedem_subida(settings):
    from app.main import create_app
    for bad in ("", "loja=curto", "semigual", "loja=" + "a" * 40 + ",twin=" + "a" * 40):
        settings.tokens = bad
        with pytest.raises(ValueError):
            create_app(settings, None)


async def test_motor_real_sem_pesos_nao_fica_pronto_e_sintese_da_503(settings):
    import httpx
    from app.main import create_app
    settings.engine = "chatterbox"
    settings.model_revision = ""
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://v") as c:
            ready = (await c.get("/readyz", headers=auth())).json()
            assert ready["ready"] is False and "VOICE_MODEL_REVISION" in ready["reason"]
            r = await c.post("/v1/synthesize", json=body(), headers=auth())
            assert r.status_code == 503 and r.json()["error"]["code"] == "engine_not_ready"


async def test_motores_nao_rodam_em_paralelo_mesmo_com_dois_workers(settings, engine):
    """Com max_concurrency=2 há 2 threads; o motor (não thread-safe) precisa continuar serializado pelo lock."""
    import httpx
    from app.main import create_app
    settings.max_concurrency = 2
    state = {"now": 0, "max": 0}
    original = engine.synthesize

    def tracked(*a, **k):
        state["now"] += 1
        state["max"] = max(state["max"], state["now"])
        try:
            return original(*a, **k)
        finally:
            state["now"] -= 1
    engine.synthesize = tracked
    engine.delay = 0.3
    app = create_app(settings, engine)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://v") as c:
            rs = await asyncio.gather(*[c.post("/v1/synthesize", json=body(f"req-par-0000{i}"), headers=auth()) for i in range(2)])
    assert [r.status_code for r in rs] == [200, 200] and state["max"] == 1


async def test_formato_invalido_na_saida_do_codificador_e_barrado(client, monkeypatch):
    """Se o codificador devolvesse algo que não é OGG/Opus mono, o serviço não entrega (probe decodifica de verdade)."""
    monkeypatch.setattr(audio, "encode_ogg_opus", lambda *a, **k: b"RIFF" + b"\0" * 64)
    r = await client.post("/v1/synthesize", json=body("req-fmt-00001"), headers=auth())
    assert r.status_code == 502 and r.json()["error"]["code"] == "invalid_audio_format"
