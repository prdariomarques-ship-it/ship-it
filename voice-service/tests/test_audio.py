import io

import av
import numpy as np
import pytest

from app import audio


def _tone(seconds=1.0, sr=24000, amp=0.3):
    t = np.arange(int(seconds * sr)) / sr
    return (amp * np.sin(2 * np.pi * 220 * t)).astype(np.float32)


def test_encode_e_probe_ida_e_volta():
    data = audio.encode_ogg_opus(_tone(1.5), 24000)
    info = audio.probe_ogg_opus(data)
    assert (info.container, info.codec, info.channels, info.sample_rate) == ("ogg", "opus", 1, 48000)
    assert abs(info.duration_seconds - 1.5) < 0.1


@pytest.mark.parametrize("sr", [8000, 16000, 22050, 24000, 44100, 48000])
def test_varias_taxas_de_amostragem_viram_48k_mono(sr):
    info = audio.probe_ogg_opus(audio.encode_ogg_opus(_tone(1.0, sr), sr))
    assert info.sample_rate == 48000 and abs(info.duration_seconds - 1.0) < 0.1


def test_pico_so_e_atenuado_nunca_amplificado():
    loud = audio.limit_peak(_tone(0.2, amp=1.0), -3.0)
    assert np.max(np.abs(loud)) <= 10 ** (-3 / 20) + 1e-6
    quiet = _tone(0.2, amp=0.05)
    assert np.array_equal(audio.limit_peak(quiet, -3.0), quiet)       # baixo continua baixo: sem ganho automático


@pytest.mark.parametrize("bad", [np.array([], dtype=np.float32), np.array([np.nan] * 100, dtype=np.float32), np.array([np.inf] * 100, dtype=np.float32)])
def test_entrada_invalida(bad):
    with pytest.raises(audio.AudioFormatError):
        audio.encode_ogg_opus(bad, 24000)


@pytest.mark.parametrize("blob", [b"", b"RIFFxxxxWAVE", b"OggS" + b"\x00" * 20, b"OggS"])
def test_probe_recusa_nao_ogg_ou_ilegivel(blob):
    with pytest.raises(audio.AudioFormatError):
        audio.probe_ogg_opus(blob)


def test_probe_recusa_estereo():
    buf = io.BytesIO()
    c = av.open(buf, "w", format="ogg")
    s = c.add_stream("libopus", rate=48000)
    s.layout = "stereo"
    frame = av.AudioFrame.from_ndarray(np.zeros((1, 2 * 48000), dtype=np.float32), format="flt", layout="stereo")
    frame.sample_rate = 48000
    for p in s.encode(frame):
        c.mux(p)
    for p in s.encode(None):
        c.mux(p)
    c.close()
    with pytest.raises(audio.AudioFormatError, match="canais"):
        audio.probe_ogg_opus(buf.getvalue())


def test_probe_recusa_codec_diferente_de_opus():
    codecs = [c for c in ("libvorbis",) if c in av.codecs_available]
    if not codecs:
        pytest.skip("sem encoder vorbis nesta build do PyAV")
    buf = io.BytesIO()
    c = av.open(buf, "w", format="ogg")
    s = c.add_stream(codecs[0], rate=48000)
    s.layout = "mono"
    frame = av.AudioFrame.from_ndarray(_tone(1.0, 48000).reshape(1, -1), format="fltp", layout="mono")
    frame.sample_rate = 48000
    for p in s.encode(frame):
        c.mux(p)
    for p in s.encode(None):
        c.mux(p)
    c.close()
    with pytest.raises(audio.AudioFormatError, match="opus"):
        audio.probe_ogg_opus(buf.getvalue())


def test_probe_ogg_truncado():
    data = audio.encode_ogg_opus(_tone(2.0), 24000)
    with pytest.raises(audio.AudioFormatError):
        audio.probe_ogg_opus(data[: len(data) // 8])
