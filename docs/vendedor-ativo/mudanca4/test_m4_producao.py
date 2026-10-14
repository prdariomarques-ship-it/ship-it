# ruff: noqa: F811
"""Mudança 4 sobre o handlers.py REAL de producao (f7b07719 + Mudança 2A bf3ff6b7 + Mudança 4).

SQLite real; so o gateway, o LLM e o portao de risco sao substituidos. Prova: contato da lista (por id ou por telefone) fica sem resposta e gera UM alerta
ao dono por janela; contato fora da lista continua respondendo; o arquivo e lido a cada chamada (sem reiniciar); arquivo ausente = comportamento anterior.
NAO prova o comportamento no Postgres de producao nem com o Evolution real."""
import sys
import types

import pytest

sys.path.insert(0, "tests")
from test_m2a_producao import (  # noqa: E402,F401  (fixtures e helpers da 2A)
    PERSONAL, _jobs, _run_twin, _twin_inbound, handlers, twin, w,
)

OWNER = "5511900000099"


@pytest.fixture
def lista(monkeypatch, tmp_path):
    caminho = tmp_path / "twin_silent_contacts.txt"
    monkeypatch.setenv("TWIN_SILENT_FILE", str(caminho))
    return caminho


async def test_contato_da_lista_por_id_fica_em_silencio_e_gera_um_alerta(twin, lista):
    cid, mid = await _twin_inbound(twin, "5511911000001", "Amor, passa no mercado?")
    lista.write_text(f"# familia\n{cid}  # Elaine\n", encoding="utf-8")
    await _run_twin(twin, cid, mid)
    jobs = await _jobs(twin)
    assert twin.box.calls == 0
    assert [j.payload["to"] for j in jobs] == [OWNER] and "contato prioritário" in jobs[0].payload["content"]


async def test_contato_da_lista_por_telefone_com_ou_sem_ddi(twin, lista):
    cid, mid = await _twin_inbound(twin, "5511911000002", "Oi")
    lista.write_text("11911000002\n", encoding="utf-8")
    await _run_twin(twin, cid, mid)
    assert twin.box.calls == 0 and [j.payload["to"] for j in await _jobs(twin)] == [OWNER]
    cid2, mid2 = await _twin_inbound(twin, "11911000003", "Oi")
    lista.write_text("+55 (11) 91100-0003\n", encoding="utf-8")
    await _run_twin(twin, cid2, mid2)
    assert twin.box.calls == 0 and [j.payload["to"] for j in await _jobs(twin)] == [OWNER, OWNER]


async def test_contato_fora_da_lista_continua_respondendo(twin, lista):
    cid, mid = await _twin_inbound(twin, "5511911000004", "Vai hoje?")
    lista.write_text("999999\n5511999999999\n", encoding="utf-8")
    await _run_twin(twin, cid, mid)
    (job,) = await _jobs(twin)
    assert twin.box.calls == 1 and job.payload["to"] == "5511911000004" and job.payload["content"] == "Vou sim."


async def test_o_arquivo_e_lido_a_cada_chamada_sem_reiniciar(twin, lista):
    cid, mid = await _twin_inbound(twin, "5511911000005", "Oi")
    await _run_twin(twin, cid, mid)  # arquivo ainda nao existe: responde como antes
    assert twin.box.calls == 1 and [j.payload["to"] for j in await _jobs(twin)] == ["5511911000005"]
    cid2, mid2 = await _twin_inbound(twin, "5511911000006", "Oi")
    lista.write_text(f"{cid2}\n", encoding="utf-8")
    await _run_twin(twin, cid2, mid2)
    assert twin.box.calls == 1 and [j.payload["to"] for j in await _jobs(twin)] == ["5511911000005", OWNER]
    lista.write_text("# esvaziada\n", encoding="utf-8")
    cid3, mid3 = await _twin_inbound(twin, "5511911000007", "Oi")
    await _run_twin(twin, cid3, mid3)
    assert twin.box.calls == 2


async def test_varias_mensagens_seguidas_do_mesmo_contato_geram_um_alerta_so(twin, lista):
    cid, mid = await _twin_inbound(twin, "5511911000008", "Oi")
    lista.write_text(f"{cid}\n", encoding="utf-8")
    await _run_twin(twin, cid, mid)
    from models.message import MessageDirection

    from test_m2a_producao import _msg

    async with twin.sessions() as db:
        from repositories.contact import ContactRepository

        contact = await ContactRepository(db).get(cid)
        from datetime import datetime, timezone

        contact.awaiting_reply_since = datetime.now(timezone.utc)
        await db.commit()
    mid2 = await _msg(twin, cid, MessageDirection.INBOUND, "Cadê você?", instance=PERSONAL, minutes_ago=0)
    await _run_twin(twin, cid, mid2)
    jobs = await _jobs(twin)
    assert twin.box.calls == 0 and [j.payload["to"] for j in jobs] == [OWNER]  # o segundo ficou em silencio e sem novo alerta


def test_entradas_do_arquivo(monkeypatch, tmp_path):
    caminho = tmp_path / "x.txt"
    monkeypatch.setenv("TWIN_SILENT_FILE", str(caminho))
    caminho.write_text("14, 31\n  # so comentario\n5511965493260 # Elaine\n\nlixo\n+55 (11) 91100-0003\n", encoding="utf-8")
    assert handlers._twin_silent_entries() == ["14", "31", "5511965493260", "lixo", "+55 (11) 91100-0003"]
    assert handlers._twin_silent_contact(14, None) and handlers._twin_silent_contact(31, "") and not handlers._twin_silent_contact(15, "")
    assert handlers._twin_silent_contact(99, "+55 11 96549-3260") and not handlers._twin_silent_contact(99, "5511965493261")
    assert not handlers._twin_silent_contact(1, "5511999990000")  # "lixo" nao tem digitos: ignorado
