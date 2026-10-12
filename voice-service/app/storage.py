"""Armazenamento privado e temporário dos áudios gerados. Diretório 0700, arquivos 0600, limpeza por TTL."""
from __future__ import annotations

import os
import secrets
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass
class StoredAudio:
    audio_id: str
    path: Path
    agent: str
    created: float
    size: int
    sha256: str
    duration_seconds: float


class AudioStore:
    def __init__(self, directory: Path, ttl_seconds: int) -> None:
        self.dir = Path(directory)
        self.ttl = ttl_seconds
        self.dir.mkdir(parents=True, exist_ok=True)
        os.chmod(self.dir, 0o700)
        # Tudo aqui é temporário por definição: o que sobrou de uma execução anterior é descartado na subida.
        for leftover in self.dir.glob("*.ogg"):
            leftover.unlink(missing_ok=True)
        self._items: dict[str, StoredAudio] = {}

    def put(self, agent: str, data: bytes, sha256: str, duration: float) -> StoredAudio:
        audio_id = secrets.token_urlsafe(24)
        path = self.dir / f"{audio_id}.ogg"
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        item = StoredAudio(audio_id, path, agent, time.time(), len(data), sha256, duration)
        self._items[audio_id] = item
        return item

    def get(self, audio_id: str, agent: str) -> StoredAudio | None:
        item = self._items.get(audio_id)
        if item is None or item.agent != agent or time.time() - item.created > self.ttl:
            return None
        return item

    def delete(self, audio_id: str, agent: str) -> bool:
        item = self._items.get(audio_id)
        if item is None or item.agent != agent:
            return False
        self._items.pop(audio_id, None)
        item.path.unlink(missing_ok=True)
        return True

    def sweep(self, now: float | None = None) -> int:
        now = time.time() if now is None else now
        expired = [i for i in self._items.values() if now - i.created > self.ttl]
        for item in expired:
            self._items.pop(item.audio_id, None)
            item.path.unlink(missing_ok=True)
        return len(expired)

    def count(self) -> int:
        return len(self._items)
