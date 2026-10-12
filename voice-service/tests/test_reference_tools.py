import json
import wave

import numpy as np
import pytest

from scripts import analyze_reference as ar
from scripts import prepare_reference as pr
from app.profiles import load_profile


def _speechlike(seconds=20, sr=24000, amp=0.2, noise=0.002, clip=False, hum=0.0, seed=3):
    rng = np.random.default_rng(seed)
    t = np.arange(int(seconds * sr)) / sr
    env = (np.sin(2 * np.pi * 0.4 * t) > -0.3).astype(np.float32)          # pausas
    x = amp * env * np.sin(2 * np.pi * 180 * t) * (0.6 + 0.4 * np.sin(2 * np.pi * 3 * t))
    x = x + noise * rng.standard_normal(t.size) + hum * np.sin(2 * np.pi * 60 * t)
    if clip:
        x = np.clip(x * 8, -1, 1)
    return x.astype(np.float32), sr


def _wav(path, x, sr):
    pr.write_wav16(path, x, sr)


def test_analise_limpa_vs_ruidosa_vs_clipada(tmp_path):
    clean = ar.analyze(*_speechlike())
    noisy = ar.analyze(*_speechlike(noise=0.05))
    clipped = ar.analyze(*_speechlike(clip=True))
    humming = ar.analyze(*_speechlike(hum=0.02))
    assert clean["flags"] == [] or "banda estreita" in " ".join(clean["flags"])
    assert noisy["snr_estimate_db"] < clean["snr_estimate_db"] and "relação sinal/ruído estimada baixa" in noisy["flags"]
    assert clipped["clipping_fraction"] > 0.01 and "possível distorção/clipping" in clipped["flags"]
    assert any("zumbido" in f for f in humming["flags"])
    assert clean["suggested_window"]["end_seconds"] - clean["suggested_window"]["start_seconds"] == pytest.approx(12.0, abs=0.1)


def test_analise_nao_altera_o_arquivo(tmp_path):
    p = tmp_path / "a.wav"
    _wav(p, *_speechlike(8))
    before = pr.sha256_file(p)
    x, sr, info = ar.load_mono(p)
    ar.analyze(x, sr)
    assert pr.sha256_file(p) == before and info["sample_rate_hz"] == 24000


def test_preparar_perfil_preserva_original_e_recorta_sem_filtros(tmp_path):
    src = tmp_path / "gravacao.wav"
    x, sr = _speechlike(20)
    _wav(src, x, sr)
    profiles = tmp_path / "profiles"
    rc = pr.main([str(src), "--profiles-dir", str(profiles), "--agent", "loja", "--start", "2", "--end", "14",
                  "--voice-owner", "Titular de teste", "--consent-scope", "teste", "--confirm-authorized"])
    assert rc == 0
    d = profiles / "loja"
    assert pr.sha256_file(d / "original" / "gravacao.wav") == pr.sha256_file(src)          # original intacto
    with wave.open(str(d / "reference.wav")) as w:
        assert w.getframerate() == 24000 and w.getnchannels() == 1 and w.getnframes() == 12 * 24000
        got = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").astype(np.float32) / 32767
    ref16 = np.round(x[2 * sr: 14 * sr] * 32767) / 32767                                    # só quantização a 16 bits
    assert np.max(np.abs(got - ref16)) < 1e-4                                               # nenhum filtro/ganho aplicado
    prof = load_profile(profiles, "loja")                                                   # o serviço aceita o perfil
    assert prof.consent_owner == "Titular de teste"
    meta = json.loads((d / "profile.json").read_text())
    assert meta["source"]["processing"] == "recorte + mono"


def test_preparar_exige_consentimento_e_nao_sobrescreve(tmp_path):
    src = tmp_path / "g.wav"
    _wav(src, *_speechlike(10))
    args = [str(src), "--profiles-dir", str(tmp_path / "p"), "--agent", "loja", "--start", "0", "--end", "8",
            "--voice-owner", "X", "--consent-scope", "y"]
    assert pr.main(args) == 2 and not (tmp_path / "p").exists()
    assert pr.main(args + ["--confirm-authorized"]) == 0
    assert pr.main(args + ["--confirm-authorized"]) == 2


def test_le_ogg_opus_como_o_do_whatsapp(tmp_path):
    from app import audio
    x, sr = _speechlike(15)
    p = tmp_path / "WhatsApp Ptt exemplo.ogg"
    p.write_bytes(audio.encode_ogg_opus(x, sr, bitrate=32000, peak_dbfs=-1.0))
    got, got_sr, info = ar.load_mono(p)
    assert info["codec"] == "opus" and info["container"] == "ogg" and got_sr == 48000
    assert abs(len(got) / got_sr - 15) < 0.2
    rep = ar.analyze(got, got_sr)
    assert rep["duration_seconds"] == pytest.approx(15, abs=0.2) and rep["suggested_window"] is not None
