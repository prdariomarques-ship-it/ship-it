"""Ficha do Twin (niveis, contatos, prioridade, recarga) e a trava de dados de contato nao verificaveis.

Sem rede e sem banco: so arquivos temporarios e funcoes puras. NAO prova a integracao no handler do Twin (feita a parte)."""
import json
import os

import pytest

from services import twin_ficha
from services.output_safety import unverified_contact_data
from utils.config import get_settings

FICHA = {
    "public": ["Dário Marques Neto, pastor e teólogo.", "E-mail (só se pedirem): dariomneto@hotmail.com"],
    "family_only": ["Mora em Mauá."],
    "contacts": [
        {"name": "Elaine", "relation": "esposa", "group": "family", "match": {"contact_ids": [31]}},
        {"name": "Alan", "relation": "primo", "group": "family", "match": {"phone_suffixes": ["11957862800"]}},
        {"name": "Van Prates", "relation": "chefe", "group": "priority", "match": {"phone_suffixes": ["(11) 98258-9350"]}},
        {"name": "Nathan", "relation": "", "group": "", "match": {"contact_ids": [30]}},
    ],
}


@pytest.fixture
def ficha_file(tmp_path, monkeypatch):
    path = tmp_path / "ficha.json"
    path.write_text(json.dumps(FICHA), encoding="utf-8")
    monkeypatch.setattr(get_settings(), "twin_ficha_path", str(path))
    twin_ficha._cache.clear()
    return path


def test_sem_caminho_configurado_nao_ha_ficha(monkeypatch):
    monkeypatch.setattr(get_settings(), "twin_ficha_path", "")
    assert twin_ficha.get_ficha() is None and twin_ficha.lookup(31, "5511900000000") == (None, None)
    assert twin_ficha.build_ficha_blocks(None, None) == []


@pytest.mark.parametrize("conteudo", ["{nao e json", "[]", json.dumps({"contacts": [{"name": "X", "match": {}}]}),
                                      json.dumps({"contacts": [{"name": "X", "match": {"phone_suffixes": ["123"]}}]})])
def test_arquivo_invalido_vira_sem_ficha_e_nunca_levanta(tmp_path, monkeypatch, conteudo):
    path = tmp_path / "ruim.json"
    path.write_text(conteudo, encoding="utf-8")
    monkeypatch.setattr(get_settings(), "twin_ficha_path", str(path))
    twin_ficha._cache.clear()
    assert twin_ficha.get_ficha() is None
    monkeypatch.setattr(get_settings(), "twin_ficha_path", str(tmp_path / "nao-existe.json"))
    assert twin_ficha.get_ficha() is None


def test_contato_e_achado_por_id_ou_por_final_do_telefone(ficha_file):
    ficha = twin_ficha.get_ficha()
    assert ficha.entry_for(31, "5511999999999").name == "Elaine"
    assert ficha.entry_for(None, "5511957862800").name == "Alan"
    assert ficha.entry_for(999, "+55 (11) 98258-9350").name == "Van Prates"
    assert ficha.entry_for(999, "5511900000000") is None and ficha.entry_for(None, None) is None


def test_nome_da_agenda_vence_o_nome_do_perfil_do_whatsapp(ficha_file):
    ficha, entry = twin_ficha.lookup(30, "5511992977972")
    assert twin_ficha.display_name("Jonathan", entry) == "Nathan"                 # o caso real nathan2 / "Jonathan"
    assert twin_ficha.display_name("Jonathan", None) == "Jonathan"


def test_familia_recebe_os_fatos_da_familia_e_estranho_so_os_publicos(ficha_file):
    ficha, elaine = twin_ficha.lookup(31, "5511999999999")
    familia = "\n".join(twin_ficha.build_ficha_blocks(ficha, elaine))
    assert "Mora em Mauá" in familia and "Quem está falando agora: Elaine, esposa do Dário." in familia
    _, estranho = twin_ficha.lookup(500, "5511911111111")
    publico = "\n".join(twin_ficha.build_ficha_blocks(ficha, estranho))
    assert "dariomneto@hotmail.com" in publico and "pastor e teólogo" in publico
    assert "Mauá" not in publico and "Quem está falando" not in publico


def test_prioridade_so_para_o_grupo_priority(ficha_file):
    ficha = twin_ficha.get_ficha()
    assert twin_ficha.is_priority(ficha.entry_for(None, "5511982589350"))
    assert not twin_ficha.is_priority(ficha.entry_for(31, None)) and not twin_ficha.is_priority(None)


def test_ficha_recarrega_sozinha_quando_o_arquivo_muda(ficha_file):
    assert twin_ficha.get_ficha().entry_for(31, None).name == "Elaine"
    novo = json.loads(ficha_file.read_text(encoding="utf-8"))
    novo["contacts"][0]["name"] = "Elaine M."
    ficha_file.write_text(json.dumps(novo), encoding="utf-8")
    os.utime(ficha_file, (ficha_file.stat().st_atime, ficha_file.stat().st_mtime + 5))
    assert twin_ficha.get_ficha().entry_for(31, None).name == "Elaine M."


# ------------------------------------------------------------- dados de contato nao verificaveis

PERMITIDOS = ["E-mail (só se pedirem): dariomneto@hotmail.com", "Cliente: me chama no 11 98258-9350 ou veja https://loja.exemplo.com/catalogo"]


@pytest.mark.parametrize("resposta, categoria", [
    ("Me manda em dariomarques@outlook.com", "email"),                    # o caso real 11267
    ("Olha em https://outro.exemplo.com/x", "link"),
    ("Liga no 11 91234-5678", "telefone_ou_documento"),
    ("Meu CPF é 123.456.789-09", "telefone_ou_documento"),
])
def test_dado_de_contato_inventado_e_detectado(resposta, categoria):
    assert unverified_contact_data(resposta, PERMITIDOS) == categoria


@pytest.mark.parametrize("resposta", [
    "Pode mandar para DARIOMNETO@hotmail.com",                              # maiusculas: o mesmo e-mail
    "Fala comigo no (11) 98258-9350.",                                       # mesmo numero, outra formatacao
    "Fala no +55 11 98258-9350",                                             # com codigo do pais
    "Veja https://loja.exemplo.com/catalogo.",                               # ponto final da frase
    "Vou sim, 2 latas de 18 litros às 14h.",                                 # numeros comuns nao sao contato
    "",
])
def test_dado_que_veio_da_ficha_ou_da_conversa_passa(resposta):
    assert unverified_contact_data(resposta, PERMITIDOS) is None
