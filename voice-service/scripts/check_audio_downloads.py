"""Confere uma pasta de áudios baixados e lista SÓ os que faltam ou vieram incompletos (para baixar/reenviar apenas esses).

Não altera nem apaga nada na pasta. Só lê. Gera `faltam.txt` (um nome por linha) ao lado, ou onde `--saida` indicar.

Uso (PowerShell, dentro de voice-service):
  python -m scripts.check_audio_downloads --pasta C:\\caminho\\audios
  # com a lista do que DEVERIA existir (um nome por linha; opcional ",tamanho_em_bytes"):
  python -m scripts.check_audio_downloads --pasta C:\\caminho\\audios --esperados C:\\caminho\\lista.txt

O que conta como incompleto:
  .wav   cabeçalho promete mais bytes do que o arquivo tem, ou não abre
  .ogg/.opus   a última página Ogg não tem a marca de fim de fluxo (arquivo cortado), ou não começa com "OggS"
  qualquer tipo   arquivo vazio; ou tamanho diferente do informado na lista de esperados
  .part/.crdownload/.tmp   download ainda em andamento ou interrompido
Formatos sem verificação de conteúdo (mp3, m4a, ...) só são checados por tamanho (vazio / diferente do esperado).
"""
from __future__ import annotations

import argparse
import struct
from pathlib import Path

AUDIO_SUFFIXES = {".wav", ".ogg", ".opus", ".oga", ".mp3", ".m4a", ".aac", ".flac", ".webm", ".amr"}
PARTIAL_SUFFIXES = {".part", ".crdownload", ".tmp", ".download", ".partial"}


def _check_wav(path: Path) -> str | None:
    size = path.stat().st_size
    with path.open("rb") as handle:
        head = handle.read(12)
        if len(head) < 12 or head[:4] != b"RIFF" or head[8:12] != b"WAVE":
            return "cabeçalho WAV inválido"
        if struct.unpack("<I", head[4:8])[0] + 8 > size:
            return "arquivo menor que o cabeçalho declara (cortado)"
        while True:
            chunk = handle.read(8)
            if len(chunk) < 8:
                return "sem bloco de dados"
            cid, length = chunk[:4], struct.unpack("<I", chunk[4:])[0]
            if cid == b"data":
                if length != 0xFFFFFFFF and handle.tell() + length > size:
                    return "bloco de dados cortado"
                return None
            handle.seek(length + (length & 1), 1)


def _check_ogg(path: Path) -> str | None:
    size = path.stat().st_size
    with path.open("rb") as handle:
        if handle.read(4) != b"OggS":
            return 'não começa com "OggS"'
        tail_size = min(size, 70000)  # uma página Ogg tem no máximo ~65 KB
        handle.seek(size - tail_size)
        tail = handle.read(tail_size)
    at = tail.rfind(b"OggS")
    if at < 0 or len(tail) - at < 27:
        return "última página Ogg ausente (cortado)"
    if not tail[at + 5] & 0x04:
        return "sem a marca de fim de fluxo (arquivo cortado)"
    return None


def check_file(path: Path, expected_size: int | None = None) -> str | None:
    """None se parece completo; senão o motivo."""
    suffix = path.suffix.lower()
    if suffix in PARTIAL_SUFFIXES:
        return "download em andamento ou interrompido"
    size = path.stat().st_size
    if size == 0:
        return "arquivo vazio"
    if expected_size is not None and size != expected_size:
        return f"tamanho {size} diferente do esperado {expected_size}"
    try:
        if suffix == ".wav":
            return _check_wav(path)
        if suffix in {".ogg", ".opus", ".oga"}:
            return _check_ogg(path)
    except (OSError, struct.error) as exc:
        return f"não consegui ler ({type(exc).__name__})"
    return None


def read_expected(path: Path) -> dict[str, int | None]:
    expected: dict[str, int | None] = {}
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        name, _, size = line.replace(";", ",").partition(",")
        expected[name.strip()] = int(size) if size.strip().isdigit() else None
    return expected


def run(folder: Path, expected: dict[str, int | None] | None = None) -> tuple[list[str], list[tuple[str, str]], list[str]]:
    """(ok, problemas[(nome, motivo)], faltando). Sem lista de esperados, só avalia o que está na pasta."""
    present = {p.name: p for p in folder.iterdir() if p.is_file() and (p.suffix.lower() in AUDIO_SUFFIXES | PARTIAL_SUFFIXES)}
    ok: list[str] = []
    problems: list[tuple[str, str]] = []
    for name in sorted(present):
        reason = check_file(present[name], (expected or {}).get(name))
        (problems.append((name, reason)) if reason else ok.append(name))
    missing = sorted(name for name in (expected or {}) if name not in present)
    return ok, problems, missing


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--pasta", type=Path, required=True)
    ap.add_argument("--esperados", type=Path, default=None, help="lista de nomes que deveriam existir (um por linha, opcional ',bytes')")
    ap.add_argument("--saida", type=Path, default=None, help="onde gravar faltam.txt (padrão: dentro da pasta)")
    args = ap.parse_args(argv)
    if not args.pasta.is_dir():
        print(f"pasta não encontrada: {args.pasta}")
        return 2
    expected = read_expected(args.esperados) if args.esperados else None
    ok, problems, missing = run(args.pasta, expected)
    print(f"completos: {len(ok)}   incompletos: {len(problems)}   faltando: {len(missing)}")
    for name, reason in problems:
        print(f"  INCOMPLETO  {name}: {reason}")
    for name in missing:
        print(f"  FALTANDO    {name}")
    redo = [name for name, _ in problems] + missing
    target = args.saida or (args.pasta / "faltam.txt")
    target.write_text("\n".join(redo) + ("\n" if redo else ""), encoding="utf-8")
    print(f"\nlista só dos que precisam ser baixados/enviados de novo: {target} ({len(redo)})")
    return 0 if not redo else 1


if __name__ == "__main__":
    raise SystemExit(main())
