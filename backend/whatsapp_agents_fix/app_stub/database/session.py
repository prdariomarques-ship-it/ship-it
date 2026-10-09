"""FAKE -- only needed because jobs/handlers.py imports this at module
level (used by event-bus handlers this test suite does not exercise)."""


class _FakeSessionFactory:
    def __call__(self):
        raise NotImplementedError("async_session_factory is not exercised by this test suite")


async_session_factory = _FakeSessionFactory()


async def get_db():
    raise NotImplementedError("get_db (FastAPI dependency) is not exercised by this test suite")
