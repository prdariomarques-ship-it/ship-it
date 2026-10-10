"""FAKE JobService -- records enqueue() calls for assertions instead of
actually queuing anything. The real job queue is not part of the three
source files this delivery was built from."""

ENQUEUE_CALLS: list[tuple[str, dict]] = []


class JobService:
    def __init__(self, db):
        self.db = db

    async def enqueue(self, name, payload, delay_seconds=0):
        ENQUEUE_CALLS.append((name, payload))
        return None
