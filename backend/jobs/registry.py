"""Job handler registry: map job names to async handlers.

Register with the decorator:

    @job_handler("contact.summarize")
    async def summarize(db: AsyncSession, payload: dict) -> None: ...
"""
from collections.abc import Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession

JobHandler = Callable[[AsyncSession, dict], Awaitable[None]]

_HANDLERS: dict[str, JobHandler] = {}


class UnknownJobError(KeyError):
    def __init__(self, name: str) -> None:
        super().__init__(name)
        self.name = name

    def __str__(self) -> str:
        return f"No handler registered for job {self.name!r}"


def job_handler(name: str) -> Callable[[JobHandler], JobHandler]:
    def decorator(handler: JobHandler) -> JobHandler:
        _HANDLERS[name] = handler
        return handler

    return decorator


def resolve_handler(name: str) -> JobHandler:
    try:
        return _HANDLERS[name]
    except KeyError:
        raise UnknownJobError(name) from None


def registered_jobs() -> list[str]:
    return sorted(_HANDLERS)
