"""Painel do voice-service: reutiliza o MESMO motor, fila e configuração. Testado com o motor SIMULADO (fake): prova painel, fila e
formato — NÃO prova áudio real com a voz do titular, que depende de gravação, pesos e validação na máquina escolhida."""
import asyncio


from tests.conftest import TOKEN_LOJA, TOKEN_TWIN, auth

TEXT = "Olá! Teste do painel."


def body(rid, text=TEXT):
    return {"request_id": rid, "text": text, "language": "pt"}


async def test_paginas_estaticas_sem_dado_e_com_politica_restritiva(client):
    for path, mime in (("/panel", "text/html"), ("/panel/panel.js", "text/javascript"), ("/panel/panel.css", "text/css")):
        r = await client.get(path)
        assert r.status_code == 200 and r.headers["content-type"].startswith(mime)
        assert "default-src 'none'" in r.headers["content-security-policy"] and "script-src 'self'" in r.headers["content-security-policy"]
        assert r.headers["cache-control"] == "no-store" and r.headers["x-content-type-options"] == "nosniff"
        assert TOKEN_LOJA not in r.text
    html = (await client.get("/panel")).text
    assert "<script src=\"/panel/panel.js\">" in html and "onclick" not in html and "<script>" not in html     # sem script inline


async def test_js_nao_usa_innerhtml_e_guarda_token_so_em_memoria(client):
    js = (await client.get("/panel/panel.js")).text
    assert "innerHTML" not in js and "localStorage" not in js and "sessionStorage" not in js and "document.cookie" not in js


async def test_status_exige_token(client):
    for headers in ({}, {"Authorization": "Bearer errado"}):
        assert (await client.get("/v1/panel/status", headers=headers)).status_code == 401


async def test_status_com_motor_simulado_e_rotulado_como_simulado(client):
    st = (await client.get("/v1/panel/status", headers=auth())).json()
    assert st["mode"] == "simulado" and st["engine"] == "fake" and st["ready"] is True
    assert st["real_voice_possible"] is False                           # motor simulado nunca vale como voz real
    assert st["checklist"]["motor_real_configurado"] is False and st["checklist"]["pesos_carregados"] is False
    assert st["checklist"]["perfil_com_consentimento_e_referencia"] is True
    assert st["checklist"]["aprovacao_humana_das_amostras"].startswith("pendente")
    assert st["profile"]["present"] is True and st["profile"]["consent_authorized"] is True
    assert len(st["profile"]["reference_sha256_prefix"]) == 12
    assert st["queue"]["max_concurrency"] == 1 and st["queue"]["queue_max"] == 1 and st["limits"]["max_text_chars"] == 200


async def test_agente_sem_perfil_ve_perfil_inexistente(client):
    st = (await client.get("/v1/panel/status", headers=auth(TOKEN_TWIN))).json()      # há token do twin, mas não há perfil twin
    assert st["agent"] == "twin" and st["profile"]["present"] is False and st["profile_error"]
    assert st["checklist"]["perfil_com_consentimento_e_referencia"] is False


async def test_status_so_expoe_prefixo_do_hash_e_nenhum_caminho_ou_texto(client):
    await client.post("/v1/synthesize", json=body("painel-0001", "texto confidencial do cliente"), headers=auth())
    raw = (await client.get("/v1/panel/status", headers=auth())).text
    assert "texto confidencial" not in raw and "reference.wav" not in raw and str(client.settings.profiles_dir) not in raw
    assert "reference_sha256\"" not in raw                                                    # só o prefixo, nunca o hash inteiro


async def test_pedidos_recentes_usam_a_mesma_fila_e_so_mostram_metadados(client):
    r = await client.post("/v1/synthesize", json=body("painel-0002"), headers=auth())
    assert r.status_code == 200
    st = (await client.get("/v1/panel/status", headers=auth())).json()
    (rec,) = st["recent"]
    assert rec["request_id"] == "painel-0002" and rec["status"] == "ok" and rec["chars"] == len(TEXT) and set(rec) == {"at", "agent", "request_id", "status", "seconds", "chars"}
    assert st["queue"]["stored_audios"] == 1 and st["queue"]["admitted"] == 0


async def test_recusas_tambem_aparecem_no_historico(client):
    r = await client.post("/v1/synthesize", json=body("painel-0003", "x" * 500), headers=auth())
    assert r.status_code >= 400
    st = (await client.get("/v1/panel/status", headers=auth())).json()
    assert st["recent"][0]["request_id"] == "painel-0003" and st["recent"][0]["status"] != "ok"


async def test_historico_de_um_agente_nao_aparece_para_outro(client):
    await client.post("/v1/synthesize", json=body("painel-0004"), headers=auth())
    st = (await client.get("/v1/panel/status", headers=auth(TOKEN_TWIN))).json()
    assert st["recent"] == []


async def test_painel_e_vendedor_dividem_a_mesma_fila(client, engine):
    """Um pedido do 'vendedor' em andamento ocupa a capacidade que o painel enxerga e disputa: não existe fila paralela."""
    gate = asyncio.Event()
    original = engine.synthesize

    def slow(text, language, reference, reference_text):
        import time
        while not gate.is_set():
            time.sleep(0.01)
        return original(text, language, reference, reference_text)
    engine.synthesize = slow
    t1 = asyncio.create_task(client.post("/v1/synthesize", json=body("vendedor-0001"), headers=auth()))
    await asyncio.sleep(0.2)
    st = (await client.get("/v1/panel/status", headers=auth())).json()
    assert st["queue"]["inflight"] == 1 and st["queue"]["admitted"] == 1
    t2 = asyncio.create_task(client.post("/v1/synthesize", json=body("painel-0005"), headers=auth()))          # entra na espera
    await asyncio.sleep(0.2)
    r3 = await client.post("/v1/synthesize", json=body("painel-0006"), headers=auth())                         # excede a fila
    assert r3.status_code == 429
    gate.set()
    assert (await t1).status_code == 200 and (await t2).status_code == 200


async def test_status_com_motor_nao_pronto_explica_o_motivo(settings, engine):
    import httpx
    from app.engines.base import EngineNotReady
    from app.main import create_app

    def fail():
        raise EngineNotReady("pesos ausentes em /models")
    engine.load = fail
    app = create_app(settings, engine)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://voice") as c:
            st = (await c.get("/v1/panel/status", headers=auth())).json()
    assert st["ready"] is False and "pesos ausentes" in st["not_ready_reason"] and st["real_voice_possible"] is False
