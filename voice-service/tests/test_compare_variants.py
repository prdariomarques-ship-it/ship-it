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

    def generate(self, text, language_id, audio_prompt_path, exaggeration, cfg_weight, temperature=0.8,
                 repetition_penalty=1.2, min_p=0.05, top_p=1.0):
        self.calls.append((text, language_id, audio_prompt_path, exaggeration, cfg_weight, temperature, repetition_penalty))
        return _Tensor(np.sin(np.linspace(0, 440, 2400, dtype=np.float32))[None, :])


def test_parse_variant_defaults_and_errors():
    assert cv.parse_variant("cfg=0")["cfg"] == 0.0 and cv.parse_variant("cfg=0")["temp"] == 0.8
    parsed = cv.parse_variant("cfg=0.3,exg=0.7,temp=0.6,rep=1.4")
    assert (parsed["cfg"], parsed["exg"], parsed["temp"], parsed["rep"]) == (0.3, 0.7, 0.6, 1.4)
    for bad in ("cfg=2", "exg=3", "temp=0", "rep=0.5", "x=1", "cfg=", "lixo"):
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


def _write_pcm(path, seconds, rate=8000):
    import wave as w
    samples = (np.arange(int(seconds * rate)) % 100).astype("<i2")
    with w.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(samples.tobytes())
    return samples


def test_trim_wav_copies_the_exact_samples_without_changing_them(tmp_path):
    source = tmp_path / "ref.wav"
    samples = _write_pcm(source, 10)
    out = cv.trim_wav(source, tmp_path / "corte.wav", 2.0, 5.0)
    with wave.open(str(out)) as handle:
        assert handle.getframerate() == 8000 and handle.getnframes() == 3 * 8000
        data = np.frombuffer(handle.readframes(handle.getnframes()), dtype="<i2")
    assert list(data) == list(samples[2 * 8000:5 * 8000])
    with pytest.raises(ValueError):
        cv.trim_wav(source, tmp_path / "curto.wav", 1.0, 1.5)


def test_run_with_start_end_uses_the_trimmed_reference_and_extra_params(tmp_path):
    ref = tmp_path / "ref.wav"
    _write_pcm(ref, 20)
    out = tmp_path / "saida"
    fake = _FakeModel()
    rc = cv.main(["--reference", str(ref), "--out", str(out), "--device", "cpu", "--seed", "1", "--start", "7", "--end", "19",
                  "--variant", "cfg=0,temp=0.6,rep=1.4"], model_factory=lambda d, dev: fake)
    assert rc == 0 and (out / "referencia_recortada.wav").is_file()
    assert all(c[2].endswith("referencia_recortada.wav") and c[4] == 0.0 and c[5] == 0.6 and c[6] == 1.4 for c in fake.calls)
    assert cv.main(["--reference", str(ref), "--out", str(out), "--start", "1"], model_factory=lambda d, dev: fake) == 2


class _PtbrModel:
    """Imita o generate() do Space pt-BR: SÓ aceita estes parametros (rep/minp/topp dariam TypeError)."""
    sr = 24000

    def __init__(self):
        self.calls = []

    def generate(self, text, audio_prompt_path=None, exaggeration=0.5, cfg_weight=0.5, temperature=0.8, language_id="en"):
        self.calls.append((language_id, exaggeration, cfg_weight, temperature))
        return _Tensor(np.sin(np.linspace(0, 440, 2400, dtype=np.float32))[None, :])


def test_ptbr_engine_passes_only_the_space_parameters(tmp_path):
    ref = tmp_path / "ref.wav"
    ref.write_bytes(b"x")
    fake = _PtbrModel()
    out = tmp_path / "saida"
    rc = cv.main(["--reference", str(ref), "--out", str(out), "--device", "cpu", "--seed", "3", "--space-dir", str(tmp_path),
                  "--variant", "cfg=0.3,exg=0.6,temp=0.7"], model_factory=lambda d, dev: fake)
    assert rc == 0 and fake.calls == [("pt", 0.6, 0.3, 0.7)] * len(SAMPLES)
    meta = json.loads((out / "chave.json").read_text(encoding="utf-8"))
    assert meta["motor"] == "ptbr-space"


def test_ptbr_engine_rejects_parameters_the_space_does_not_have(tmp_path):
    ref = tmp_path / "ref.wav"
    ref.write_bytes(b"x")
    called = []
    rc = cv.main(["--reference", str(ref), "--out", str(tmp_path / "o"), "--device", "cpu", "--space-dir", str(tmp_path),
                  "--variant", "cfg=0,rep=1.4"], model_factory=lambda d, dev: called.append(1))
    assert rc == 2 and called == []


def test_load_ptbr_model_requires_the_downloaded_space(tmp_path):
    with pytest.raises(FileNotFoundError):
        cv.load_ptbr_model(tmp_path, "cpu")
