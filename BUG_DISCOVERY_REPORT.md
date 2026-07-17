# Bug Discovery Report — Dashboard Product Acceptance Review

One real bug was found during acceptance testing (via an actual browser-driven walkthrough, not just type-checking/lint/build). Recorded here per the "what was learned, not only what was delivered" ask.

---

## 1. `priority_score` crashes on any persisted goal with a deadline (SQLite backend)

### Title
`GET /api/goals/ready` returns `500 Internal Server Error` for any goal with a non-null `deadline`, when the database backend is SQLite.

### Root Cause
`goals/scoring.py::priority_score` computes `goal.deadline - now`, where `now` is always timezone-aware (`datetime.now(timezone.utc)`). SQLAlchemy's `DateTime(timezone=True)` column type preserves timezone info on **Postgres** but silently returns a **naive** `datetime` on read-back from **SQLite** (SQLite has no native timezone-aware storage type — this is a documented SQLAlchemy+SQLite interaction, not a SQLAlchemy bug). Subtracting an aware `datetime` from a naive one raises `TypeError: can't subtract offset-naive and offset-aware datetimes`.

`GoalService.ready_goals` calls `priority_score` on every candidate goal; the exception propagated all the way to an unhandled `500` at the API layer.

### Why existing tests missed it
Every existing test that exercises `priority_score` with a deadline constructs the `Goal` object **in memory** (`Goal(priority=..., deadline=...)`, never persisted, never re-read from a database) — see `tests/test_goals.py`'s scoring section (`test_closer_deadline_scores_higher`, `test_overdue_deadline_is_capped_not_unbounded`, etc.). The naive/aware mismatch only exists after a round trip through SQLite; a goal built purely in Python code already has whatever tzinfo the test itself supplied (always aware, in every existing case).

Separately, `test_ready_goals_ranks_by_score_not_creation_order` **does** persist goals and call `ready_goals` for real — but none of the seeded goals in that test have a `deadline` set (only `priority` varies), so the code path that subtracts `goal.deadline - now` was never reached with a persisted, deadline-bearing goal until this review's demo-data seeding did exactly that (a goal created via the real `POST /api/goals` endpoint, with a real `deadline`, then listed via `GET /api/goals/ready`).

### Fix implemented
`goals/scoring.py::priority_score` now normalizes `goal.deadline` to UTC-aware before subtracting, only when it comes back naive:

```python
deadline = goal.deadline
if deadline.tzinfo is None:
    deadline = deadline.replace(tzinfo=timezone.utc)
days_remaining = (deadline - now).total_seconds() / 86400
```

This is a no-op on Postgres (where `deadline` already carries tzinfo) and fixes the crash on SQLite, so the function is correct regardless of backend — not a workaround specific to the demo environment.

### Regression test added
`tests/test_goals.py::test_ready_goals_with_a_persisted_deadline_does_not_crash` — persists a goal with a real `deadline` via `GoalService.create_goal`, then calls `ready_goals` in a fresh session (forcing a real read-back from the database, not an in-memory object), and asserts it returns normally instead of raising. This is the exact gap described above, closed.

### Production impact
**None on the currently deployed system.** Production runs Postgres (`DATABASE_URL=postgresql+asyncpg://...`, see `docker/docker-compose.yml`), where `DateTime(timezone=True)` round-trips correctly and `deadline` is never naive — this bug cannot manifest there today. It was only discovered because this review used an **isolated SQLite-backed demo environment** to seed realistic data without touching production (see `PRODUCT_ACCEPTANCE.md`). The fix is still correct and worth shipping: it removes a real, if currently dormant, footgun — anyone running this codebase against SQLite (a local dev setup without Docker/Postgres, a future test environment, a lighter-weight deployment) would hit this exact `500` the first time they created a goal with a deadline and asked for `ready_goals`.

### Risk level
**Low.** The fix is a 4-line, purely defensive normalization with no behavior change on the only backend production actually uses (Postgres). Full backend suite (875 tests, including the new regression test) passes; `ruff` and `mypy` clean on both changed files.

### Files changed
- `backend/goals/scoring.py` — the fix (tzinfo normalization).
- `backend/tests/test_goals.py` — new regression test.
