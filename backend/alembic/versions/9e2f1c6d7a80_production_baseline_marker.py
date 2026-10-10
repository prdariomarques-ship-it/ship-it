"""Baseline marker for the real production alembic head.

CI finding (round 4, "rode a CI completa"): `alembic upgrade head` /
`alembic downgrade base` against a BLANK database (exactly what CI's
"Migrations apply and roll back" step does, and what this PR's own
e610080001/002/003 migrations were never actually exercised against
until the earlier CI-blocking lint/type-check failures were fixed) raised
`KeyError: '9e2f1c6d7a80'` the instant alembic tried to build its
revision map -- e610080001_pause_control.py's `down_revision` points at
this id, which was never a file in this repository's own history: it is
the real production alembic head, confirmed via direct introspection
against darioos_cutover_20260927 (see that file's own docstring: "Revises:
9e2f1c6d7a80 (verified source head, not an applied-database assertion)").
This repository's migration history never included whatever created the
real schema up to that point in production -- the same documented gap as
handlers.py/router.py's missing baseline (see SESSION_TRACKING.md).

This file is a pure no-op (upgrade/downgrade both do nothing) -- it only
gives alembic a revision id to chain onto, so the chain can be walked from
a blank database instead of crashing. It is deliberately NOT a claim that
production's real history at this point was empty; it is a placeholder
for content this repository does not have and cannot safely guess.

Zero effect on the real production database: production's own
`alembic_version` is already at or past this revision (its tracked state
predates e610080001/002/003 entirely, which came from this PR, not from
production), so `alembic upgrade head` run there will skip straight past
this revision and never execute its upgrade()/downgrade() at all. It only
matters for a blank database that has none of these tables yet (CI, a
fresh local/test environment) -- exactly the gap this PR's own migrations
exposed by finally being reachable in CI.

Also a merge point: `6f32d7549a9a` and `2cc4e7d820a6` were already two
independent heads in this repository's chain (both children of
`a1f9c3d84e2b`, a genuine branch split that predates this PR) before
e610080001 was ever added -- `alembic upgrade head` (singular, as CI's
own workflow invokes it) requires exactly one head to target, so this
merge is required for that command to keep working, not optional cleanup.

Revision ID: 9e2f1c6d7a80
Revises: 6f32d7549a9a, 2cc4e7d820a6
"""
from alembic import op  # noqa: F401
import sqlalchemy as sa  # noqa: F401

revision = '9e2f1c6d7a80'
down_revision = ('6f32d7549a9a', '2cc4e7d820a6')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
