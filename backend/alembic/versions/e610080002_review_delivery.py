"""Explicitly close uncertain delivery without asserting remote non-delivery.

Revision ID: e610080002
Revises: e610080001
Legacy and crashed transports default unfinished and cannot be closed.
"""
from alembic import op
import sqlalchemy as sa

revision = 'e610080002'
down_revision = 'e610080001'
branch_labels = None
depends_on = None


def upgrade():
    for table, check, statuses in (
        ('conversation_send_intents', 'ck_send_status', "'suppressed','needs_review','sent','closed_unknown'"),
        ('conversation_alert_intents', 'ck_alert_status', "'pending','needs_review','sent','closed_unknown'"),
    ):
        # Batch mode rebuilds SQLite tables, preserving checks, keys and indexes;
        # PostgreSQL uses ordinary ALTER TABLE under the same migration.
        with op.batch_alter_table(table) as batch:
            batch.add_column(sa.Column('transport_finished', sa.Boolean(), nullable=False,
                                       server_default=sa.false()))
            batch.drop_constraint(check, type_='check')
            batch.create_check_constraint(check, f'status IN ({statuses})')
    with op.batch_alter_table('conversation_control_audit') as batch:
        batch.add_column(sa.Column('prior_revision', sa.BigInteger(), nullable=True))
        batch.add_column(sa.Column('intent_kind', sa.String(16), nullable=True))
        batch.add_column(sa.Column('intent_key', sa.String(255), nullable=True))


def downgrade():
    # CI finding (round 4, "rode a CI completa"): this unconditional refusal
    # made `alembic downgrade base` -- CI's own "Migrations apply and roll
    # back" smoke test, run against a BLANK database -- impossible to ever
    # pass, regardless of anything else in this PR. The concern it protects
    # (closed delivery outcomes / audit history) is about real data, not
    # about whether a downgrade is attempted at all -- same reasoning this
    # round applied to e610080003's downgrade. Refuse only when there is
    # real data to lose; a blank/fresh database (CI, a new environment) has
    # none, and reverting there is genuinely safe.
    bind = op.get_bind()
    has_real_data = bind.execute(sa.text(
        "SELECT 1 WHERE EXISTS (SELECT 1 FROM conversation_send_intents WHERE transport_finished IS TRUE) "
        "OR EXISTS (SELECT 1 FROM conversation_alert_intents WHERE transport_finished IS TRUE) "
        "OR EXISTS (SELECT 1 FROM conversation_control_audit WHERE prior_revision IS NOT NULL "
        "OR intent_kind IS NOT NULL OR intent_key IS NOT NULL)"
    )).first()
    if has_real_data is not None:
        raise RuntimeError(
            'Refusing to downgrade e610080002: conversation_send_intents / '
            'conversation_alert_intents have closed outcomes, or '
            'conversation_control_audit has review metadata, that only this '
            "migration's columns record. Dropping them now would destroy "
            'real closed-outcome/audit history. To go back past this point, '
            'restore from a tested backup taken before that decision.'
        )

    for table, check, statuses in (
        ('conversation_send_intents', 'ck_send_status', "'suppressed','needs_review','sent'"),
        ('conversation_alert_intents', 'ck_alert_status', "'pending','needs_review','sent'"),
    ):
        with op.batch_alter_table(table) as batch:
            batch.drop_constraint(check, type_='check')
            batch.create_check_constraint(check, f'status IN ({statuses})')
            batch.drop_column('transport_finished')
    with op.batch_alter_table('conversation_control_audit') as batch:
        batch.drop_column('intent_key')
        batch.drop_column('intent_kind')
        batch.drop_column('prior_revision')
