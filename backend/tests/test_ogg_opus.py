"""Validação estrutural do áudio de voz (services/ogg_opus.py), com fixtures geradas de tons sintéticos."""
import struct
from pathlib import Path

import pytest

from services.ogg_opus import InvalidVoiceAudio, inspect_ogg_opus

FIX = Path(__file__).parent / "fixtures" / "voice"
MONO = (FIX / "tone_2s_mono.ogg").read_bytes()
STEREO = (FIX / "tone_1s_stereo.ogg").read_bytes()
LIMITS = dict(max_bytes=4_000_000, max_seconds=40.0)


def test_aceita_ogg_opus_mono_e_mede_a_duracao():
    info = inspect_ogg_opus(MONO, **LIMITS)
    assert info.channels == 1 and abs(info.duration_seconds - 2.0) < 0.1 and info.pages >= 3 and info.size_bytes == len(MONO)


@pytest.mark.parametrize("blob, trecho", [
    (b"", "vazio"),
    (b"RIFF" + b"\0" * 100, "OggS"),
    (b"OggS", "truncada"),
    (MONO[: len(MONO) // 2], None),                 # truncado: sem marca de fim de fluxo ou página cortada
    (MONO[:-5], None),
])
def test_recusa_vazio_ou_nao_ogg_ou_truncado(blob, trecho):
    with pytest.raises(InvalidVoiceAudio) as e:
        inspect_ogg_opus(blob, **LIMITS)
    if trecho:
        assert trecho in str(e.value)


def test_recusa_estereo():
    with pytest.raises(InvalidVoiceAudio, match="mono"):
        inspect_ogg_opus(STEREO, **LIMITS)


def test_recusa_codec_que_nao_e_opus():
    broken = bytearray(MONO)
    i = broken.index(b"OpusHead")
    broken[i:i + 8] = b"vorbisXX"
    with pytest.raises(InvalidVoiceAudio, match="OpusHead"):
        inspect_ogg_opus(bytes(broken), **LIMITS)


def test_recusa_acima_do_tamanho_e_da_duracao():
    with pytest.raises(InvalidVoiceAudio, match="tamanho"):
        inspect_ogg_opus(MONO, max_bytes=1000, max_seconds=40.0)
    with pytest.raises(InvalidVoiceAudio, match="duração"):
        inspect_ogg_opus(MONO, max_bytes=4_000_000, max_seconds=1.0)


def test_recusa_curto_demais():
    with pytest.raises(InvalidVoiceAudio, match="curto"):
        inspect_ogg_opus(MONO, max_bytes=4_000_000, max_seconds=40.0, min_seconds=5.0)


def test_recusa_pagina_fora_de_sequencia():
    data = bytearray(MONO)
    # troca o número de sequência da 2ª página (offset 18 do cabeçalho de página)
    first_len = 27 + data[26] + sum(data[27:27 + data[26]])
    struct.pack_into("<I", data, first_len + 18, 7)
    with pytest.raises(InvalidVoiceAudio, match="sequência"):
        inspect_ogg_opus(bytes(data), **LIMITS)
