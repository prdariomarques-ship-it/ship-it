"""Parâmetros do Chatterbox chegam ao modelo (cfg_weight, exaggeration), com o modelo SUBSTITUÍDO por um duplo: não prova qualidade nem
carrega pesos. A conditional é guardada por (referência, expressividade)."""
import pytest
from pydantic import ValidationError

from app.config import VoiceSettings
from app.engines.chatterbox_engine import ChatterboxEngine


class FakeModel:
    sr = 24000

    def __init__(self):
        self.prepared, self.generated, self.conds = [], [], None

    def prepare_conditionals(self, path, exaggeration=0.5):
        self.prepared.append((path, exaggeration))
        self.conds = f"conds:{path}:{exaggeration}"

    def generate(self, text, language_id, exaggeration=0.5, cfg_weight=0.5, **_):
        self.generated.append((text, language_id, exaggeration, cfg_weight, self.conds))
        import torch
        return torch.zeros(1, 24000)


def _engine(tmp_path, **kw):
    s = VoiceSettings(tokens="loja=" + "a" * 40, storage_dir=tmp_path / "t", profiles_dir=tmp_path / "p", **kw)
    e = ChatterboxEngine(s)
    e._model = FakeModel()
    return e


def test_parametros_padrao_do_upstream(tmp_path):
    pytest.importorskip("torch")
    e = _engine(tmp_path)
    e.synthesize("olá", "pt", tmp_path / "ref.wav", None)
    assert e._model.generated[0][1:4] == ("pt", 0.5, 0.5) and e._model.prepared == [(str(tmp_path / "ref.wav"), 0.5)]


def test_parametros_configurados_chegam_ao_modelo_e_a_conditional_e_reaproveitada(tmp_path):
    pytest.importorskip("torch")
    e = _engine(tmp_path, chatterbox_cfg_weight=0.3, chatterbox_exaggeration=0.7)
    e.synthesize("um", "pt", tmp_path / "ref.wav", None)
    e.synthesize("dois", "pt", tmp_path / "ref.wav", None)
    assert [g[2:4] for g in e._model.generated] == [(0.7, 0.3), (0.7, 0.3)]
    assert len(e._model.prepared) == 1                                   # mesma referência e mesma expressividade: prepara uma vez
    assert e._model.generated[1][4] == "conds:" + str(tmp_path / "ref.wav") + ":0.7"


def test_outra_referencia_gera_outra_conditional(tmp_path):
    pytest.importorskip("torch")
    e = _engine(tmp_path)
    e.synthesize("um", "pt", tmp_path / "a.wav", None)
    e.synthesize("dois", "pt", tmp_path / "b.wav", None)
    assert len(e._model.prepared) == 2 and e._model.generated[1][4].endswith("b.wav:0.5")


@pytest.mark.parametrize("field, value", [("chatterbox_cfg_weight", -0.1), ("chatterbox_cfg_weight", 1.5), ("chatterbox_exaggeration", -1), ("chatterbox_exaggeration", 2.5)])
def test_valores_fora_da_faixa_derrubam_a_carga(tmp_path, field, value):
    with pytest.raises(ValidationError, match=field):
        VoiceSettings(tokens="loja=" + "a" * 40, **{field: value})
