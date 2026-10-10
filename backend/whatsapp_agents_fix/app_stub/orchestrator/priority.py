from enum import Enum


class Priority(str, Enum):
    URGENT = "urgent"
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"


def quick_priority_hint(text):
    return Priority.NORMAL
