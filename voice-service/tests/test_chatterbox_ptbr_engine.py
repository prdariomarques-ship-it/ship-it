"""Motor `chatterbox_ptbr`: carga offline com pesos fixados, recusa de mistura com outro pacote `chatterbox`, parâmetros aprovados na escuta
(cfg 0.3, exg 0.7, temp 0.8) chegando ao modelo. O pacote do Space é SUBSTITUÍDO por um duplo gravado em disco: não prova qualidade nem
carrega pesos reais (a validação real é a escuta no PC do titular)."""
import sys
import textwrap
from pathlib import Path

import numpy as np
import pytest
from pydantic import ValidationError

from app.config import VoiceSettings
from app.engines import build_engine
from app.engines.base import EngineError, EngineNotReady
from app.engines.chatterbox_ptbr_engine import ChatterboxPtBrEngine

FAKE_TTS = textwrap.dedent(
    '''
    S3GEN_FILENAME = "s3gen_v3.pt"
    T3_FILENAME = "t3_pt_br.safetensors"
    TOKENIZER_FILENAME = "grapheme_mtl_merged_expanded_v1.json"
    CALLS = []


    class _Wav:
        def __init__(self, n):
            self._n = n

        def squeeze(self):
            return self

        def detach(self):
            return self

        def cpu(self):
            return self

        def numpy(self):
            return __import__("numpy").full(self._n, 0.25, dtype="float64")


    class ChatterboxTTS:
        sr = 24000

        def __init__(self):
            self.conds = None
            self.prepared, self.generated = [], []

        @classmethod
        def from_local(cls, ckpt_dir, device, t3_filename=None, s3gen_filename=None):
            CALLS.append((str(ckpt_dir), device, t3_filename, s3gen_filename))
            return cls()

        def prepare_conditionals(self, path, exaggeration=0.5):
            self.prepared.append((path, exaggeration))
            self.conds = f"conds:{path}:{exaggeration}"

        def generate(self, text, audio_prompt_path=None, exaggeration=0.5, cfg_weight=0.5, temperature=0.8, language_id="en"):
            if text == "explode":
                raise RuntimeError("cuda out of memory")
            self.generated.append((text, language_id, exaggeration, cfg_weight, temperature, self.conds))
            return _Wav(2400)
    '''
)


@pytest.fixture
def space(tmp_path):
    """Pasta de 'Space' falso + isolamento de sys.path/sys.modules (o pacote 'chatterbox' falso não vaza para outros testes)."""
    saved_path, saved_mods = list(sys.path), {k: v for k, v in sys.modules.items() if k == "chatterbox" or k.startswith("chatterbox.")}
    for k in saved_mods:
        del sys.modules[k]
    pkg = tmp_path / "space" / "chatterbox" / "src" / "chatterbox"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "tts.py").write_text(FAKE_TTS, encoding="utf-8")
    yield tmp_path / "space"
    sys.path[:] = saved_path
    for k in [k for k in sys.modules if k == "chatterbox" or k.startswith("chatterbox.")]:
        del sys.modules[k]
    sys.modules.update(saved_mods)


@pytest.fixture
def weights(tmp_path):
    d = tmp_path / "models"
    d.mkdir()
    for name in ("ve.pt", "grapheme_mtl_merged_expanded_v1.json", "t3_pt_br.safetensors", "s3gen_v3.pt"):
        (d / name).write_bytes(b"x")
    return d


def _settings(tmp_path, space, weights, **kw):
    base = dict(
        tokens="loja=" + "a" * 40, engine="chatterbox_ptbr", device="cuda", model_revision="base-aaaaaaaaaaaa+ptbr-bbbbbbbbbbbb",
        model_dir=weights, ptbr_space_dir=space, storage_dir=tmp_path / "t", profiles_dir=tmp_path / "p",
    )
    base.update(kw)
    return VoiceSettings(**base)


def _loaded(tmp_path, space, weights, **kw):
    e = ChatterboxPtBrEngine(_settings(tmp_path, space, weights, **kw))
    e.load()
    return e


def test_build_engine_devolve_o_motor_ptbr(tmp_path, space, weights):
    assert isinstance(build_engine(_settings(tmp_path, space, weights)), ChatterboxPtBrEngine)


def test_carga_usa_a_pasta_de_pesos_e_os_nomes_do_proprio_space(tmp_path, space, weights, monkeypatch):
    monkeypatch.delenv("HF_HUB_OFFLINE", raising=False)
    _loaded(tmp_path, space, weights)
    import chatterbox.tts as tts

    assert tts.CALLS == [(str(weights), "cuda", "t3_pt_br.safetensors", "s3gen_v3.pt")]
    import os
    assert os.environ["HF_HUB_OFFLINE"] == "1"                      # o serviço nunca vai à rede


def test_sem_revisao_nao_carrega(tmp_path, space, weights):
    with pytest.raises(EngineNotReady, match="VOICE_MODEL_REVISION vazio"):
        ChatterboxPtBrEngine(_settings(tmp_path, space, weights, model_revision="")).load()


def test_revisao_acima_de_64_caracteres_nao_carrega(tmp_path, space, weights):
    with pytest.raises(EngineNotReady, match="64"):
        ChatterboxPtBrEngine(_settings(tmp_path, space, weights, model_revision="x" * 65)).load()


def test_sem_pasta_do_space_nao_carrega(tmp_path, space, weights):
    with pytest.raises(EngineNotReady, match="VOICE_PTBR_SPACE_DIR"):
        ChatterboxPtBrEngine(_settings(tmp_path, None, weights)).load()


def test_pasta_do_space_sem_tts_py_nao_carrega(tmp_path, space, weights):
    with pytest.raises(EngineNotReady, match="tts.py"):
        ChatterboxPtBrEngine(_settings(tmp_path, tmp_path / "vazia", weights)).load()


def test_pesos_ausentes_sao_listados(tmp_path, space, weights):
    (weights / "s3gen_v3.pt").unlink()
    (weights / "ve.pt").unlink()
    with pytest.raises(EngineNotReady) as err:
        ChatterboxPtBrEngine(_settings(tmp_path, space, weights)).load()
    assert "s3gen_v3.pt" in str(err.value) and "ve.pt" in str(err.value) and "t3_pt_br" not in str(err.value)


def test_outro_pacote_chatterbox_ja_carregado_e_recusado(tmp_path, space, weights, monkeypatch):
    outro = tmp_path / "pypi" / "chatterbox"
    outro.mkdir(parents=True)
    (outro / "__init__.py").write_text("", encoding="utf-8")
    import importlib.util

    spec = importlib.util.spec_from_file_location("chatterbox", outro / "__init__.py")
    mod = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, "chatterbox", mod)
    with pytest.raises(EngineNotReady, match="outro pacote 'chatterbox'"):
        ChatterboxPtBrEngine(_settings(tmp_path, space, weights)).load()


def test_parametros_configurados_chegam_ao_modelo_e_a_conditional_e_reaproveitada(tmp_path, space, weights):
    e = _loaded(tmp_path, space, weights, chatterbox_cfg_weight=0.3, chatterbox_exaggeration=0.7, chatterbox_temperature=0.6)
    ref = tmp_path / "ref.wav"
    a = e.synthesize("um", "pt", ref, None)
    e.synthesize("dois", "pt", ref, None)
    m = e._model
    assert [g[1:5] for g in m.generated] == [("pt", 0.7, 0.3, 0.6), ("pt", 0.7, 0.3, 0.6)]
    assert m.prepared == [(str(ref), 0.7)]                           # mesma referência e expressividade: prepara uma vez
    assert m.generated[1][5] == f"conds:{ref}:0.7"
    assert a.sample_rate == 24000 and a.samples.dtype == np.float32 and a.samples.ndim == 1 and a.samples.size == 2400


def test_outra_expressividade_gera_outra_conditional(tmp_path, space, weights):
    e = _loaded(tmp_path, space, weights)
    ref = tmp_path / "ref.wav"
    e.synthesize("um", "pt", ref, None)
    e._settings.chatterbox_exaggeration = 0.9
    e.synthesize("dois", "pt", ref, None)
    assert [p[1] for p in e._model.prepared] == [0.5, 0.9]


def test_sintese_antes_de_carregar(tmp_path, space, weights):
    with pytest.raises(EngineNotReady, match="não carregado"):
        ChatterboxPtBrEngine(_settings(tmp_path, space, weights)).synthesize("oi", "pt", Path("r.wav"), None)


def test_falha_do_modelo_vira_engine_error(tmp_path, space, weights):
    e = _loaded(tmp_path, space, weights)
    with pytest.raises(EngineError, match="cuda out of memory"):
        e.synthesize("explode", "pt", tmp_path / "ref.wav", None)


@pytest.mark.parametrize("value", [0.0, 0.04, 2.5])
def test_temperatura_fora_da_faixa(value):
    with pytest.raises(ValidationError, match="chatterbox_temperature"):
        VoiceSettings(tokens="loja=" + "a" * 40, chatterbox_temperature=value)


def test_padrao_do_servico_e_o_aprovado_na_escuta_de_temperatura(tmp_path, space, weights):
    e = _loaded(tmp_path, space, weights, chatterbox_cfg_weight=0.3, chatterbox_exaggeration=0.7)
    e.synthesize("um", "pt", tmp_path / "ref.wav", None)
    assert e._model.generated[0][1:5] == ("pt", 0.7, 0.3, 0.8)          # temperatura padrão = a da variante C


def test_variaveis_de_ambiente_com_prefixo_voice(monkeypatch, tmp_path):
    monkeypatch.setenv("VOICE_ENGINE", "chatterbox_ptbr")
    monkeypatch.setenv("VOICE_PTBR_SPACE_DIR", str(tmp_path))
    monkeypatch.setenv("VOICE_CHATTERBOX_CFG_WEIGHT", "0.3")
    monkeypatch.setenv("VOICE_CHATTERBOX_EXAGGERATION", "0.7")
    monkeypatch.setenv("VOICE_CHATTERBOX_TEMPERATURE", "0.8")
    s = VoiceSettings(tokens="loja=" + "a" * 40)
    assert (s.engine, s.ptbr_space_dir, s.chatterbox_cfg_weight, s.chatterbox_exaggeration, s.chatterbox_temperature) == (
        "chatterbox_ptbr", tmp_path, 0.3, 0.7, 0.8)
