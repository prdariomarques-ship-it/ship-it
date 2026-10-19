"""State persisted in a volume: poller offsets, last scheduled slot, alert/filing de-duplication."""
from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path


class FileStateStore:
    """One small JSON document, written atomically (tmp + replace). Thread-safe within a process."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = threading.Lock()
        path.parent.mkdir(parents=True, exist_ok=True)
        self._data: dict[str, str] = self._load()

    def _load(self) -> dict[str, str]:
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        except (OSError, ValueError):
            # A corrupt state file must not stop the bots, but it must not be silent either: keep a copy.
            try:
                os.replace(self._path, self._path.with_suffix(".corrupt"))
            except OSError:
                pass
            return {}
        return {str(k): str(v) for k, v in raw.items()} if isinstance(raw, dict) else {}

    def get(self, key: str) -> str | None:
        with self._lock:
            return self._data.get(key)

    def set(self, key: str, value: str) -> None:
        with self._lock:
            self._data[key] = value
            fd, tmp = tempfile.mkstemp(dir=self._path.parent, prefix=".state-", suffix=".tmp")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as fh:
                    json.dump(self._data, fh, ensure_ascii=False, sort_keys=True)
                os.replace(tmp, self._path)
            except BaseException:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
                raise

    def keys_with_prefix(self, prefix: str) -> list[str]:
        with self._lock:
            return [k for k in self._data if k.startswith(prefix)]

    def delete(self, key: str) -> None:
        with self._lock:
            if self._data.pop(key, None) is None:
                return
            fd, tmp = tempfile.mkstemp(dir=self._path.parent, prefix=".state-", suffix=".tmp")
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(self._data, fh, ensure_ascii=False, sort_keys=True)
            os.replace(tmp, self._path)
