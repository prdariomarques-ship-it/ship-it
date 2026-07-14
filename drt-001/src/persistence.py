"""
Persistence abstraction layer.
Allows swapping storage implementations without changing Runtime code.
"""

import json
import os
import threading
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, Optional
import hashlib


class IPersistence(ABC):
    """Abstract interface for persistence operations."""

    @abstractmethod
    def save(self, execution_id: str, data: Dict[str, Any]) -> None:
        """Save execution data."""
        pass

    @abstractmethod
    def load(self, execution_id: str) -> Optional[Dict[str, Any]]:
        """Load execution data."""
        pass

    @abstractmethod
    def exists(self, execution_id: str) -> bool:
        """Check if execution exists."""
        pass

    @abstractmethod
    def delete(self, execution_id: str) -> None:
        """Delete execution data."""
        pass

    @abstractmethod
    def list_executions(self) -> list[str]:
        """List all execution IDs."""
        pass

    @abstractmethod
    def validate_storage(self) -> bool:
        """Validate storage is accessible and writable."""
        pass

    @abstractmethod
    def get_wal_checkpoint(self) -> Optional[Dict[str, Any]]:
        """Get last WAL checkpoint."""
        pass

    @abstractmethod
    def write_wal(self, event: Dict[str, Any]) -> None:
        """Write event to write-ahead log."""
        pass


class FilePersistence(IPersistence):
    """File-based persistence implementation with write-ahead log."""

    def __init__(self, base_path: str = ".runtime"):
        self.base_path = Path(base_path)
        self.executions_path = self.base_path / "executions"
        self.wal_path = self.base_path / "wal.jsonl"
        self.checkpoint_path = self.base_path / "checkpoint.json"
        self.wal_lock = threading.Lock()

    def validate_storage(self) -> bool:
        """Validate storage is accessible and writable."""
        try:
            self.base_path.mkdir(parents=True, exist_ok=True)
            self.executions_path.mkdir(parents=True, exist_ok=True)

            # Test write access
            test_file = self.base_path / ".test_write"
            test_file.write_text("test")
            test_file.unlink()

            # Check disk space (basic check)
            stat = os.statvfs(self.base_path)
            available_bytes = stat.f_bavail * stat.f_frsize
            if available_bytes < 1_000_000:  # Less than 1MB
                return False

            return True
        except Exception:
            return False

    def save(self, execution_id: str, data: Dict[str, Any]) -> None:
        """Save execution data with checksum."""
        # Ensure storage is ready
        self.executions_path.mkdir(parents=True, exist_ok=True)

        execution_file = self.executions_path / f"{execution_id}.json"

        # Add checksum to detect corruption
        data_copy = data.copy()
        data_str = json.dumps(data_copy, sort_keys=True, default=str)
        checksum = hashlib.sha256(data_str.encode()).hexdigest()
        data_copy["_checksum"] = checksum

        # Write atomically: write to temp file, then rename
        temp_file = execution_file.with_suffix(".tmp")
        temp_file.write_text(json.dumps(data_copy, indent=2, default=str))
        temp_file.replace(execution_file)

    def load(self, execution_id: str) -> Optional[Dict[str, Any]]:
        """Load execution data and verify checksum."""
        execution_file = self.executions_path / f"{execution_id}.json"

        if not execution_file.exists():
            return None

        try:
            data = json.loads(execution_file.read_text())
            stored_checksum = data.pop("_checksum", None)

            if stored_checksum:
                data_str = json.dumps(data, sort_keys=True, default=str)
                computed_checksum = hashlib.sha256(data_str.encode()).hexdigest()
                if computed_checksum != stored_checksum:
                    raise ValueError(f"Checksum mismatch for {execution_id}")

            return data
        except Exception as e:
            raise ValueError(f"Failed to load execution {execution_id}: {e}")

    def exists(self, execution_id: str) -> bool:
        """Check if execution exists."""
        execution_file = self.executions_path / f"{execution_id}.json"
        return execution_file.exists()

    def delete(self, execution_id: str) -> None:
        """Delete execution data."""
        execution_file = self.executions_path / f"{execution_id}.json"
        if execution_file.exists():
            execution_file.unlink()

    def list_executions(self) -> list[str]:
        """List all execution IDs."""
        if not self.executions_path.exists():
            return []
        return [
            f.stem
            for f in self.executions_path.glob("*.json")
            if f.name != "checkpoint.json"
        ]

    def write_wal(self, event: Dict[str, Any]) -> None:
        """Append event to write-ahead log (JSONL format) with atomic protection."""
        with self.wal_lock:
            self.wal_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.wal_path, "a") as f:
                f.write(json.dumps(event, default=str) + "\n")

            # Update checkpoint atomically within lock
            self.checkpoint_path.write_text(json.dumps(event, indent=2, default=str))

    def get_wal_checkpoint(self) -> Optional[Dict[str, Any]]:
        """Get last WAL checkpoint."""
        if not self.checkpoint_path.exists():
            return None
        try:
            return json.loads(self.checkpoint_path.read_text())
        except Exception:
            return None
