"""Untracked-history placeholder, NOT a verified reconstruction of production.

STATUS: BLOCKED. Review finding (round 6, "não inventar a migração
histórica ausente"): the previous version of this file's docstring
presented its merge parentage as settled fact. It was not. Here is the
honest state, after an exhaustive `git log --all -p -S'9e2f1c6d7a80'`
across every branch and every commit in this repository (280 commits
total): the ONLY place the string "9e2f1c6d7a80" appears anywhere in this
repository's history is (a) this file, (b) SESSION_TRACKING.md, and (c)
e610080001_pause_control.py's own docstring -- all three written during
this same review engagement, none of them an independently retrievable
artifact. The claim that production's real alembic head id is
"9e2f1c6d7a80" traces back to a human relaying real VPS command output
earlier in this engagement (not fabricated this round) -- but this
repository has ZERO record of that revision's actual upgrade()/
downgrade() content, its real parent revision(s), or the full chain of
revisions production actually applied to reach it. Nothing here
confirms, for example, that production's schema really has gone through
`6f32d7549a9a` ("Create table products and add store_customers.segment")
or `2cc4e7d820a6` ("tasks and calendar contact_id") specifically -- those
two were picked as this revision's `down_revision` ONLY because they were
already this repository's own two pre-existing chain heads, not because
of any production evidence that production's real history passes through
either of them. That was an invented merge, not a recovered one, and
presenting it as "the" baseline would have been exactly the kind of
fabricated provenance this round's review explicitly prohibits.

This review has no VPS shell access and could not re-verify any of this
against the live database. Recovering the real content is BLOCKED on
that access -- it is not something further local searching can resolve.

Given that, this file now does the ONLY thing it can honestly do: give
alembic *a* revision id to chain onto so this repository's OWN migration
graph is mechanically traversable (for local dev, CI, and this review's
own test harness) instead of crashing with `KeyError: '9e2f1c6d7a80'`.
It is explicitly NOT a claim that:
  - production's real revision 9e2f1c6d7a80 had empty upgrade()/downgrade()
    content (it almost certainly did not -- something created the real
    schema up to that point);
  - production's real history passes through `6f32d7549a9a` and/or
    `2cc4e7d820a6` specifically, as opposed to some other combination, a
    different set of revisions entirely, or a schema shaped by tooling
    outside Alembic altogether;
  - a successful `alembic upgrade head` / `downgrade base` cycle against
    a BLANK database (SQLite or an isolated PostgreSQL -- both are
    exercised by this review's own tests) proves anything about
    equivalence with production. It proves only that THIS repository's
    own graph, as it exists right now, is internally traversable -- never
    run this chain's `upgrade()` against a real copy of production or any
    database that already has production-shaped data: the migrations
    between here and `e610080001` (6f32d7549a9a, 2cc4e7d820a6, and
    everything under them) are ordinary, non-idempotent historical
    migrations from before this review engagement, with no introspection
    guards, and could attempt to (re)create objects production may
    already have via a different, undocumented path.

Zero effect on the real production database EITHER way: production's own
`alembic_version` is already at or past whatever "9e2f1c6d7a80" really
represents there (its tracked state predates e610080001/002/003 entirely,
which came from this PR, not from production), so `alembic upgrade head`
run there will skip straight past this revision and never execute this
file's upgrade()/downgrade() at all, regardless of what they contain.

Next step, when unblocked: recover production's real `alembic_version`
history up to this point (every revision id actually applied, in order,
and ideally each one's real upgrade()/downgrade() source) directly from
the VPS, and replace this placeholder's parentage with that real chain --
not a guess at which locally-available heads happen to close the graph.

Revision ID: 9e2f1c6d7a80
Revises: 6f32d7549a9a, 2cc4e7d820a6 (UNVERIFIED -- see above)
"""
import alembic.op as op  # noqa: F401
import sqlalchemy as sa  # noqa: F401

revision = '9e2f1c6d7a80'
down_revision = ('6f32d7549a9a', '2cc4e7d820a6')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
