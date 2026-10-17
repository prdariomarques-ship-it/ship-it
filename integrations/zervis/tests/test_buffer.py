from zervis_bridge.buffer import EventBuffer


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def ev(i):
    return {"name": "job.done", "occurred_at": "t", "payload": {"job_id": i}}


def test_cursor_returns_only_newer_events():
    buf = EventBuffer(10, 60)
    for i in range(3):
        buf.append(ev(i))
    first = buf.since(0)
    assert [e["seq"] for e in first["events"]] == [1, 2, 3]
    assert first["next_seq"] == 3 and not first["gap"]
    assert buf.since(3)["events"] == []
    buf.append(ev(3))
    assert [e["seq"] for e in buf.since(3)["events"]] == [4]


def test_ring_overflow_reports_a_gap():
    buf = EventBuffer(2, 60)
    for i in range(5):
        buf.append(ev(i))
    result = buf.since(1)
    assert result["gap"] is True
    assert [e["seq"] for e in result["events"]] == [4, 5]


def test_ttl_expiry_reports_a_gap_and_advances_the_cursor():
    clock = Clock()
    buf = EventBuffer(10, 60, clock=clock)
    buf.append(ev(0))
    clock.now = 120
    result = buf.since(0)
    assert result["events"] == [] and result["gap"] is True
    assert result["next_seq"] == 1


def test_no_gap_when_caught_up_on_empty_buffer():
    result = EventBuffer(10, 60).since(0)
    assert result == {"events": [], "next_seq": 0, "latest_seq": 0, "gap": False}


def test_limit_pages_without_losing_events():
    buf = EventBuffer(10, 60)
    for i in range(5):
        buf.append(ev(i))
    page = buf.since(0, limit=2)
    assert [e["seq"] for e in page["events"]] == [1, 2] and page["next_seq"] == 2
    assert [e["seq"] for e in buf.since(page["next_seq"], limit=10)["events"]] == [
        3,
        4,
        5,
    ]
