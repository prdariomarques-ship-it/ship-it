"""Central logging configuration with optional structured (JSON) output."""
import json
import logging
import sys
from datetime import datetime, timezone

TEXT_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | [%(request_id)s] | %(message)s"


class RequestIDFilter(logging.Filter):
    """Stamps every record with the current request's correlation id (or
    "-" outside of a request, e.g. the job worker) — one place that reads
    the contextvar, so neither formatter needs its own copy of this logic."""

    def filter(self, record: logging.LogRecord) -> bool:
        # Deferred import: observability.request_context has no dependency on
        # this module, so this can't cycle — kept local since logging is
        # configured before the rest of the app finishes importing.
        from observability.request_context import get_request_id

        record.request_id = get_request_id() or "-"
        return True


class JsonFormatter(logging.Formatter):
    """One JSON object per line — ready for Loki/ELK/CloudWatch ingestion."""

    def format(self, record: logging.LogRecord) -> str:
        entry: dict = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname.lower(),
            "logger": record.name,
            "message": record.getMessage(),
        }
        request_id = getattr(record, "request_id", "-")
        if request_id != "-":
            entry["request_id"] = request_id
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        extra = getattr(record, "context", None)
        if isinstance(extra, dict):
            entry.update(extra)
        return json.dumps(entry, ensure_ascii=False, default=str)


def configure_logging(level: int = logging.INFO, json_output: bool = False) -> None:
    from services.log_redaction import LogRedactionFilter

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter() if json_output else logging.Formatter(TEXT_FORMAT))
    handler.addFilter(RequestIDFilter())
    handler.addFilter(LogRedactionFilter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
