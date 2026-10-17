"""compact_pauses: só o silêncio longo é cortado; a fala é copiada sem alteração; o original não é tocado."""
import wave

import numpy as np
import pytest

from scripts import compact_pauses as cp

SR = 24000


def burst(seconds: float, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    t = np.arange(int(seconds * SR)) / SR
    return (8000 * np.sin(2 * np.pi * 180 * t) * (0.6 + 0.4 * rng.random(t.size))).astype("<i2")


def gap(seconds: float) -> np.ndarray:
    return np.zeros(int(seconds * SR), dtype="<i2")


def write(path, x):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(np.asarray(x, dtype="<i2").tobytes())


def test_pausa_longa_encolhe_e_a_fala_fica_identica():
    a, b = burst(1.0, 1), burst(1.0, 2)
    x = np.concatenate([a, gap(2.0), b])
    y = cp.compact_pauses(x, SR)
    assert len(y) == pytest.approx(len(a) + len(b) + 0.2 * SR, abs=0.02 * SR)
    assert np.array_equal(y[: len(a)], a) and np.array_equal(y[-len(b):], b)    # fala copiada, sem ganho nem filtro


def test_pausa_curta_nao_e_tocada():
    x = np.concatenate([burst(1.0, 1), gap(0.28), burst(1.0, 2)])       # 0,28 s < 0,30 s: ficaria 0,20 s se fosse cortada
    y = cp.compact_pauses(x, SR)
    assert np.array_equal(y, x[: len(y)]) and len(y) >= len(x) - int(SR * 0.02)


def test_silencio_nas_pontas_perde_so_o_lado_de_fora():
    x = np.concatenate([gap(1.5), burst(1.0, 1), gap(1.5)])
    y = cp.compact_pauses(x, SR)
    assert len(y) == pytest.approx(SR * (1.0 + 0.1 + 0.1), abs=0.03 * SR)       # 0,1 s de cada ponta, junto da fala


def test_max_seconds_limita():
    x = np.concatenate([burst(3.0, 1), gap(1.0), burst(3.0, 2)])
    assert len(cp.compact_pauses(x, SR, max_seconds=4.0)) == 4 * SR


def test_audio_sem_sinal_e_recusado():
    with pytest.raises(ValueError, match="sem sinal"):
        cp.compact_pauses(gap(2.0), SR)


def test_keep_maior_que_metade_da_pausa_minima_e_recusado():
    with pytest.raises(ValueError, match="keep"):
        cp.compact_pauses(burst(1.0, 1), SR, keep=0.2, min_pause=0.3)


def test_cli_grava_outro_arquivo_e_nao_toca_o_original(tmp_path, capsys):
    src, dst = tmp_path / "o.wav", tmp_path / "d.wav"
    write(src, np.concatenate([burst(1.0, 1), gap(2.0), burst(1.0, 2)]))
    before = src.read_bytes()
    assert cp.main([str(src), str(dst)]) == 0
    assert src.read_bytes() == before and dst.is_file()
    out = capsys.readouterr().out
    assert "original:" in out and "compacta:" in out
    y, sr = cp.read_wav_mono16(dst)
    assert sr == SR and len(y) < 2.5 * SR


def test_cli_recusa_destino_igual_a_origem(tmp_path):
    src = tmp_path / "o.wav"
    write(src, burst(1.0, 1))
    with pytest.raises(SystemExit, match="próprio arquivo"):
        cp.main([str(src), str(src)])


def test_cli_recusa_wav_que_nao_e_16_bits(tmp_path):
    src = tmp_path / "o.wav"
    with wave.open(str(src), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(1)
        w.setframerate(SR)
        w.writeframes(bytes(1000))
    with pytest.raises(SystemExit, match="16 bits"):
        cp.main([str(src), str(tmp_path / "d.wav")])
