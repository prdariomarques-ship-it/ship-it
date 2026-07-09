"""Central logging configuration."""
import logging
import sys

LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"


def configure_logging(level: int = logging.INFO) -> None:
    logging.basicConfig(level=level, format=LOG_FORMAT, stream=sys.stdout, force=True)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
