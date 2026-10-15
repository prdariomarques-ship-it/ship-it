"""compare_variants: lógica de variações, escrita de WAV e chave do teste às cegas (modelo simulado; NÃO prova qualidade de voz)."""
import json
import wave

import numpy as np
import pytest

from scripts import compare_variants as cv
from scripts.samples import SAMPLES


class _Tensor:
    def __init__(self, arr):
        self.arr = arr

    def squeeze(self):
        return self

    def detach(self):
        return self

    def cpu(self):
        return self

    def numpy(self):
        return self.arr


class _FakeModel:
    sr = 24000

    def __init__(self):
        self.calls = []

    def generate(self, text, language_id, audio_prompt_path, exaggeration, cfg_weight):
        self.calls.append((text, language_id, audio_prompt_path, exaggeration, cfg_weight))
        return _Tensor(np.sin(np.linspace(0, 440, 2400, dtype=np.float32))[None, :])


def test_parse_variant_defaults_and_errors():
    assert cv.parse_variant("cfg=0") == {"cfg": 0.0, "exg": 0.5}
    assert cv.parse_variant("cfg=0.3,exg=0.7") == {"cfg": 0.3, "exg": 0.7}
    for bad in ("cfg=2", "exg=3", "x=1", "cfg=", "lixo"):
        with pytest.raises(ValueError):
            cv.parse_variant(bad)


def test_write_wav_is_mono_16bit(tmp_path):
    cv.write_wav(tmp_path / "a.wav", np.array([0.0, 2.0, -2.0], dtype=np.float32), 24000)
    with wave.open(str(tmp_path / "a.wav")) as w:
        assert (w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()) == (1, 2, 24000, 3)
        frames = np.frombuffer(w.readframes(3), dtype="<i2")
    assert list(frames) == [0, 32767, -32767]  # saturação, sem estouro


def test_blind_run_writes_files_and_key(tmp_path):
    ref = tmp_path / "ref.wav"
    ref.write_bytes(b"x")
    out = tmp_path / "saida"
    fake = _FakeModel()
    rc = cv.main(["--reference", str(ref), "--out", str(out), "--device", "cpu", "--seed", "7"], model_factory=lambda d, dev: fake)
    assert rc == 0
    assert len(fake.calls) == 3 * len(SAMPLES)
    assert all(c[1] == "pt" and c[2] == str(ref) for c in fake.calls)
    names = sorted(p.name for p in out.glob("*.wav"))
    assert names == sorted(f"{l}_{n}.wav" for l in "ABC" for n in SAMPLES)
    key = json.loads((out / "chave.json").read_text(encoding="utf-8"))["variacoes"]
    assert sorted(key) == ["A", "B", "C"]
    assert sorted((v["cfg"], v["exg"]) for v in key.values()) == [(0.0, 0.5), (0.3, 0.7), (0.5, 0.5)]


def test_missing_reference_stops_before_loading_model(tmp_path):
    called = []
    rc = cv.main(["--reference", str(tmp_path / "nao.wav"), "--out", str(tmp_path / "o"), "--device", "cpu"], model_factory=lambda d, dev: called.append(1))
    assert rc == 2 and called == []
