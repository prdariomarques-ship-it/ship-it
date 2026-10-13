"""D03 — bordas de contrato do serviço: idempotência por request_id com CONTEÚDO diferente e troca de perfil/referência.

Um retorno antigo não pode ser confundido com uma nova síntese: mesmo request_id com texto diferente (ou com outra referência de
voz) é conflito explícito (409), nunca o áudio anterior devolvido em silêncio."""
import hashlib
import shutil

from tests.conftest import auth, make_profile, write_reference

A = "Olá! Seu orçamento está pronto para retirada."
B = "Olá! Seu pedido saiu para entrega agora."


def body(rid, text):
    return {"request_id": rid, "text": text, "language": "pt"}


async def test_mesmo_request_id_com_o_mesmo_texto_e_idempotente(client, engine):
    r1 = await client.post("/v1/synthesize", json=body("idem-0001", A), headers=auth())
    r2 = await client.post("/v1/synthesize", json=body("idem-0001", A), headers=auth())
    assert r1.status_code == r2.status_code == 200 and r1.json()["audio_id"] == r2.json()["audio_id"]
    assert len(engine.calls) == 1                                     # gerou uma vez


async def test_mesmo_request_id_com_texto_diferente_e_conflito_e_nao_devolve_o_audio_antigo(client, engine):
    r1 = await client.post("/v1/synthesize", json=body("idem-0002", A), headers=auth())
    assert r1.status_code == 200
    r2 = await client.post("/v1/synthesize", json=body("idem-0002", B), headers=auth())
    assert r2.status_code == 409 and r2.json()["error"]["code"] == "request_id_conflict"
    assert len(engine.calls) == 1                                     # nada foi gerado para o texto B
    # o áudio original continua acessível e o mesmo pedido original continua idempotente
    assert (await client.get(f"/v1/audio/{r1.json()['audio_id']}", headers=auth())).status_code == 200
    assert (await client.post("/v1/synthesize", json=body("idem-0002", A), headers=auth())).json()["audio_id"] == r1.json()["audio_id"]


async def test_espacos_e_quebras_de_linha_nao_contam_como_conteudo_diferente(client, engine):
    r1 = await client.post("/v1/synthesize", json=body("idem-0003", A), headers=auth())
    r2 = await client.post("/v1/synthesize", json=body("idem-0003", "  Olá!   Seu orçamento\n está pronto para retirada. "), headers=auth())
    assert r2.status_code == 200 and r2.json()["audio_id"] == r1.json()["audio_id"]


async def test_conflito_tambem_vale_enquanto_o_primeiro_pedido_esta_em_andamento(client, engine):
    import asyncio
    import time
    gate = []
    original = engine.synthesize

    def slow(text, language, reference, reference_text):
        while not gate:
            time.sleep(0.01)
        return original(text, language, reference, reference_text)
    engine.synthesize = slow
    t1 = asyncio.create_task(client.post("/v1/synthesize", json=body("idem-0004", A), headers=auth()))
    await asyncio.sleep(0.2)
    r2 = await client.post("/v1/synthesize", json=body("idem-0004", B), headers=auth())
    gate.append(1)
    assert r2.status_code == 409 and (await t1).status_code == 200


async def test_agentes_diferentes_com_o_mesmo_request_id_nao_colidem(client, settings):
    make_profile(settings.profiles_dir, "twin")
    r1 = await client.post("/v1/synthesize", json=body("idem-0005", A), headers=auth())
    from tests.conftest import TOKEN_TWIN
    r2 = await client.post("/v1/synthesize", json=body("idem-0005", B), headers=auth(TOKEN_TWIN))
    assert r1.status_code == r2.status_code == 200 and r1.json()["audio_id"] != r2.json()["audio_id"]


async def test_troca_da_referencia_sem_mudar_o_profile_json_nao_usa_perfil_em_cache(client, settings):
    """O arquivo de referência é substituído e o profile.json NÃO muda: o serviço recusa (SHA-256 não confere) em vez de continuar
    com o perfil em cache e a referência antiga/nova misturadas."""
    ok = await client.post("/v1/synthesize", json=body("prof-0001", A), headers=auth())
    assert ok.status_code == 200
    ref = settings.profiles_dir / "loja" / "reference.wav"
    write_reference(ref, seconds=9.0)                                 # outra gravação, mesmo nome, profile.json intacto
    r = await client.post("/v1/synthesize", json=body("prof-0002", B), headers=auth())
    assert r.status_code == 404 and r.json()["error"]["code"] == "profile_unavailable"
    assert "SHA-256" in r.json()["error"]["message"]


async def test_perfil_atualizado_corretamente_vale_para_novos_pedidos_e_nao_reaproveita_resultado_antigo(client, settings):
    import json
    r1 = await client.post("/v1/synthesize", json=body("prof-0003", A), headers=auth())
    ref = settings.profiles_dir / "loja" / "reference.wav"
    write_reference(ref, seconds=9.0)
    meta_path = settings.profiles_dir / "loja" / "profile.json"
    meta = json.loads(meta_path.read_text())
    meta["reference_sha256"] = hashlib.sha256(ref.read_bytes()).hexdigest()
    meta_path.write_text(json.dumps(meta))
    r2 = await client.post("/v1/synthesize", json=body("prof-0003", A), headers=auth())     # mesmo request_id e texto, NOVA referência
    assert r2.status_code == 409 and r2.json()["error"]["code"] == "request_id_conflict"
    r3 = await client.post("/v1/synthesize", json=body("prof-0004", A), headers=auth())
    assert r3.status_code == 200 and r3.json()["reference_sha256"] == meta["reference_sha256"] != r1.json()["reference_sha256"]


async def test_remocao_do_perfil_derruba_o_uso(client, settings):
    assert (await client.post("/v1/synthesize", json=body("prof-0005", A), headers=auth())).status_code == 200
    shutil.rmtree(settings.profiles_dir / "loja")
    assert (await client.post("/v1/synthesize", json=body("prof-0006", B), headers=auth())).status_code == 404
