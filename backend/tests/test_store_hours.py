"""Horário de atendimento da loja: o que o proprietário informou em 12/10/2026 (seg–sex 08:30–17:30, sáb e feriados 08:30–12:30),
feriados, domingo sem horário presumido, validação na carga e a ferramenta do agente. Dados fictícios."""
import json
from datetime import date, datetime, time as _time, timedelta, timezone

import pytest
from pydantic import ValidationError

from services import store_hours as h
from utils.config import Settings


def cfg(**kw):
    return Settings(_env_file=None, **kw)


@pytest.fixture
def s():
    return cfg()


def utc(y, m, d, hh, mm):          # hora local de São Paulo (UTC-3, sem horário de verão desde 2019)
    return datetime(y, m, d, hh + 3, mm, tzinfo=timezone.utc)


def test_horario_informado_pelo_proprietario_e_o_padrao(s):
    assert h.hours_on(date(2026, 10, 7), s) == (_time(8, 30), _time(17, 30))     # quarta
    assert h.hours_on(date(2026, 10, 10), s) == (_time(8, 30), _time(12, 30))    # sábado
    assert h.hours_on(date(2026, 10, 11), s) is None                               # domingo: NÃO informado
    assert h.describe(s) == ("segunda a sexta: 08:30 às 17:30; sábado: 08:30 às 12:30; feriados: 08:30 às 12:30. "
                             "Domingo: sem atendimento informado — confirme com a equipe.")


@pytest.mark.parametrize("d, nome", [
    (date(2026, 1, 1), "Confraternização Universal"), (date(2026, 4, 3), "Sexta-feira Santa"), (date(2026, 4, 21), "Tiradentes"),
    (date(2026, 5, 1), "Dia do Trabalho"), (date(2026, 9, 7), "Independência do Brasil"), (date(2026, 10, 12), "Nossa Senhora Aparecida"),
    (date(2026, 11, 2), "Finados"), (date(2026, 11, 15), "Proclamação da República"), (date(2026, 11, 20), "Consciência Negra"),
    (date(2026, 12, 25), "Natal"), (date(2027, 3, 26), "Sexta-feira Santa"),
])
def test_feriados_presumidos(s, d, nome):
    assert h.holiday_name(d, s) == nome


def test_pascoa_calculada_corretamente():
    assert [h.easter(y) for y in (2024, 2025, 2026, 2027, 2028)] == [date(2024, 3, 31), date(2025, 4, 20), date(2026, 4, 5), date(2027, 3, 28), date(2028, 4, 16)]


def test_feriado_usa_horario_de_feriado_e_nao_o_do_dia_util(s):
    assert h.hours_on(date(2026, 11, 20), s) == (_time(8, 30), _time(12, 30))     # sexta, feriado
    assert h.is_open(utc(2026, 11, 20, 12, 0), s) is True and h.is_open(utc(2026, 11, 20, 14, 0), s) is False
    assert h.is_open(utc(2026, 11, 19, 14, 0), s) is True                            # quinta normal, 14:00 aberto


def test_feriado_em_domingo_nao_cria_horario_presumido(s):
    assert date(2026, 11, 15).weekday() == 6 and h.holiday_name(date(2026, 11, 15), s) == "Proclamação da República"
    assert h.hours_on(date(2026, 11, 15), s) is None


def test_feriados_extras_e_excluidos_da_loja():
    extra = cfg(store_extra_holidays="2026-12-08, 2026-07-09")          # ex.: feriados locais cadastrados pela equipe
    assert h.holiday_name(date(2026, 12, 8), extra) == "feriado cadastrado pela loja" and h.hours_on(date(2026, 12, 8), extra) == (_time(8, 30), _time(12, 30))
    excl = cfg(store_excluded_holidays="2026-11-02")
    assert h.holiday_name(date(2026, 11, 2), excl) is None and h.hours_on(date(2026, 11, 2), excl) == (_time(8, 30), _time(17, 30))


@pytest.mark.parametrize("moment, aberto", [
    (utc(2026, 10, 7, 8, 29), False), (utc(2026, 10, 7, 8, 30), True), (utc(2026, 10, 7, 17, 29), True), (utc(2026, 10, 7, 17, 30), False),
    (utc(2026, 10, 10, 12, 29), True), (utc(2026, 10, 10, 12, 30), False), (utc(2026, 10, 11, 10, 0), False),
])
def test_aberto_ou_fechado_nos_limites(s, moment, aberto):
    assert h.is_open(moment, s) is aberto


def test_margem_de_fechamento(s):
    assert h.is_open(utc(2026, 10, 7, 17, 10), s) is True and h.is_open(utc(2026, 10, 7, 17, 10), s, close_margin=timedelta(minutes=30)) is False


def test_proxima_abertura(s):
    assert h.next_open(utc(2026, 10, 7, 18, 0), s) == utc(2026, 10, 8, 8, 30)
    assert h.next_open(utc(2026, 10, 10, 13, 0), s) == utc(2026, 10, 12, 8, 30)       # sábado à tarde -> segunda (feriado) 08:30
    assert h.next_open(utc(2026, 10, 7, 10, 0), s) == utc(2026, 10, 7, 10, 0)
    with pytest.raises(h.StoreHoursError):
        h.next_open(utc(2026, 10, 7, 10, 0), cfg(store_hours="{}"))


@pytest.mark.parametrize("raw", ["", "nao-json", "[]", '{"mon": ["08:30"]}', '{"mon": ["25:00", "26:00"]}', '{"mon": ["17:00", "08:00"]}',
                                 '{"xyz": ["08:00", "09:00"]}', '{"fri-mon": ["08:00", "09:00"]}', '{"mon": ["8h30", "17h"]}'])
def test_horario_invalido_derruba_a_carga_com_erro_claro(raw):
    with pytest.raises(ValidationError) as e:
        cfg(store_hours=raw)
    assert "store_hours" in str(e.value)


def test_data_de_feriado_invalida_derruba_a_carga():
    with pytest.raises(ValidationError, match="store_extra_holidays"):
        cfg(store_extra_holidays="2026-13-40")


def test_configuracao_personalizada_e_descrita_como_configurada():
    c = cfg(store_hours=json.dumps({"mon-fri": ["09:00", "18:00"], "sun": ["09:00", "12:00"]}))
    assert h.describe(c) == "segunda a sexta: 09:00 às 18:00; domingo: 09:00 às 12:00."
    assert h.hours_on(date(2026, 10, 11), c) == (_time(9, 0), _time(12, 0))      # domingo só existe se a loja informar


async def test_ferramenta_do_agente_responde_so_o_que_esta_configurado(s, monkeypatch):
    from agents.tools.base import ToolContext
    from agents.tools.domain import get_store_hours_tool
    monkeypatch.setattr("agents.tools.domain.get_settings", lambda: s)
    ctx = ToolContext(db=None, user=None, contact_id=None)          # type: ignore[arg-type]
    out = json.loads(await get_store_hours_tool.handler(ctx, date="2026-10-10"))
    assert out["dia_da_semana"] == "sábado" and out["horario_do_dia"] == "08:30–12:30" and out["feriado"] is None
    out = json.loads(await get_store_hours_tool.handler(ctx, date="2026-10-11"))
    assert out["dia_da_semana"] == "domingo" and out["horario_do_dia"] is None and "Domingo: sem atendimento informado" in out["horarios"]
    out = json.loads(await get_store_hours_tool.handler(ctx, date="2026-11-20"))
    assert out["feriado"] == "Consciência Negra" and out["horario_do_dia"] == "08:30–12:30"
    assert "erro" in json.loads(await get_store_hours_tool.handler(ctx, date="ontem"))
    assert "aberto_agora" in json.loads(await get_store_hours_tool.handler(ctx))


def test_agente_da_loja_tem_a_ferramenta_e_a_instrucao_de_nao_inventar_horario():
    from agents.store_agent import StoreAgent
    agent = StoreAgent()
    assert "get_store_hours" in [t.name for t in agent.tools]
    assert "nunca invente horário" in agent.system_prompt
