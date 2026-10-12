"""Validação estrutural de OGG/Opus (mensagem de voz do WhatsApp) sem dependência de FFmpeg.

Lê as páginas OGG, exige o cabeçalho OpusHead (mono, versão 0), a tabela de tags, ao menos uma página de áudio, números de
página sequenciais e granule position coerente com a duração. Não substitui ouvir o áudio, nem prova que o aparelho do
destinatário o reproduz como mensagem de voz — isso só se confirma no aparelho com a versão real do Evolution.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass


class InvalidVoiceAudio(ValueError):
    """Áudio fora do formato aceito para envio como mensagem de voz."""


@dataclass(frozen=True)
class OggOpusInfo:
    channels: int
    input_sample_rate: int
    duration_seconds: float
    pages: int
    size_bytes: int


def _pages(data: bytes):
    pos, n = 0, len(data)
    while pos < n:
        if data[pos:pos + 4] != b"OggS":
            raise InvalidVoiceAudio("página OGG inválida (marca 'OggS' ausente)")
        if pos + 27 > n:
            raise InvalidVoiceAudio("página OGG truncada")
        version, header_type, granule, serial, seq, _crc, nseg = struct.unpack("<BBqIIIB", data[pos + 4: pos + 27])
        if version != 0:
            raise InvalidVoiceAudio("versão de OGG não suportada")
        table_end = pos + 27 + nseg
        if table_end > n:
            raise InvalidVoiceAudio("página OGG truncada")
        body_len = sum(data[pos + 27: table_end])
        end = table_end + body_len
        if end > n:
            raise InvalidVoiceAudio("página OGG truncada")
        yield header_type, granule, serial, seq, data[table_end:end]
        pos = end


def inspect_ogg_opus(data: bytes, *, max_bytes: int, max_seconds: float, min_seconds: float = 0.4) -> OggOpusInfo:
    if not data or len(data) > max_bytes:
        raise InvalidVoiceAudio("áudio vazio ou acima do tamanho máximo")
    pages = list(_pages(data))
    if len(pages) < 3:
        raise InvalidVoiceAudio("OGG com páginas de menos (cabeçalho, tags e áudio)")
    serial = pages[0][2]
    if any(p[2] != serial for p in pages):
        raise InvalidVoiceAudio("mais de um fluxo lógico no OGG")
    if [p[3] for p in pages] != list(range(len(pages))):
        raise InvalidVoiceAudio("números de página fora de sequência")
    first_type, first_granule, _s, _q, body = pages[0]
    if not (first_type & 0x02):
        raise InvalidVoiceAudio("primeira página sem marca de início de fluxo")
    if first_granule != 0 or len(body) < 19 or body[:8] != b"OpusHead":
        raise InvalidVoiceAudio("cabeçalho OpusHead ausente: o codec não é Opus")
    version, channels, pre_skip, rate = body[8], body[9], struct.unpack("<H", body[10:12])[0], struct.unpack("<I", body[12:16])[0]
    if version != 1:
        raise InvalidVoiceAudio("versão do OpusHead não suportada")
    if channels != 1:
        raise InvalidVoiceAudio(f"{channels} canais: a mensagem de voz precisa ser mono")
    if pages[1][4][:8] != b"OpusTags":
        raise InvalidVoiceAudio("tabela OpusTags ausente")
    if not (pages[-1][0] & 0x04):
        raise InvalidVoiceAudio("OGG sem marca de fim de fluxo (arquivo truncado)")
    granule = pages[-1][1]
    if granule <= pre_skip:
        raise InvalidVoiceAudio("OGG sem amostras de áudio")
    seconds = (granule - pre_skip) / 48000.0
    if seconds < min_seconds:
        raise InvalidVoiceAudio("áudio curto demais")
    if seconds > max_seconds:
        raise InvalidVoiceAudio("áudio acima da duração máxima")
    return OggOpusInfo(channels, rate, seconds, len(pages), len(data))
