"""Durable per-contact, per-instance pause, dispatch fences and audit.

Revision ID: e610080001
Revises: 9e2f1c6d7a80 -- production's real alembic head id, confirmed via
a human relaying real VPS command output earlier in this review
engagement. That confirms the ID only, not its content, real parent
chain, or the full history production actually applied to reach it --
none of that is recoverable from this repository or this session (no VPS
shell access here). See alembic/versions/9e2f1c6d7a80_production_baseline_marker.py
for the current, explicitly-marked-BLOCKED status of that gap, and do
not treat its placeholder content/parentage as anything more than a
local graph-traversal convenience.
"""
import alembic.op as op
import sqlalchemy as sa

revision = 'e610080001'
down_revision = '9e2f1c6d7a80'
branch_labels = None
depends_on = None


def scope_columns():
    return [sa.Column('contact_id', sa.Integer(), sa.ForeignKey('contacts.id'), nullable=False),
            sa.Column('instance', sa.String(255), nullable=False)]


def timestamp():
    return sa.Column('created_at', sa.DateTime(timezone=True), nullable=False,
                     server_default=sa.func.current_timestamp())


def upgrade():
    op.create_table('conversation_controls', *scope_columns(),
                    sa.Column('revision', sa.BigInteger(), nullable=False, server_default='0'),
                    sa.Column('paused', sa.Boolean(), nullable=False, server_default=sa.false()),
                    sa.Column('inflight', sa.String(255), nullable=True),
                    sa.PrimaryKeyConstraint('contact_id', 'instance'),
                    sa.CheckConstraint('revision >= 0', name='ck_control_revision'))
    op.create_table('conversation_control_audit',
                    sa.Column('id', sa.String(36), primary_key=True), *scope_columns(),
                    sa.Column('revision', sa.BigInteger(), nullable=False),
                    sa.Column('action', sa.String(16), nullable=False),
                    sa.Column('event_id', sa.String(255), nullable=True),
                    sa.Column('reason', sa.Text(), nullable=True),
                    sa.Column('actor_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
                    timestamp(),
                    sa.UniqueConstraint('contact_id', 'instance', 'event_id', name='uq_control_event'),
                    sa.UniqueConstraint('contact_id', 'instance', 'revision', name='uq_control_audit_revision'))
    op.create_table('conversation_send_intents',
                    sa.Column('id', sa.String(255), primary_key=True), *scope_columns(),
                    sa.Column('revision', sa.BigInteger(), nullable=True),
                    sa.Column('status', sa.String(24), nullable=False),
                    sa.Column('receipt_id', sa.String(255), nullable=True), timestamp(),
                    sa.CheckConstraint("status IN ('suppressed','needs_review','sent')", name='ck_send_status'))
    op.create_table('conversation_receipts', *scope_columns(),
                    sa.Column('external_id', sa.String(255), nullable=False), timestamp(),
                    sa.PrimaryKeyConstraint('contact_id', 'instance', 'external_id'))
    op.create_table('conversation_alert_intents', *scope_columns(),
                    sa.Column('dedup_key', sa.String(255), nullable=False),
                    sa.Column('status', sa.String(24), nullable=False, server_default='pending'),
                    sa.Column('receipt_id', sa.String(255), nullable=True), timestamp(),
                    sa.PrimaryKeyConstraint('contact_id', 'instance', 'dedup_key'),
                    sa.CheckConstraint("status IN ('pending','needs_review','sent')", name='ck_alert_status'))
    op.create_index('ix_alert_status', 'conversation_alert_intents', ['status', 'created_at'])


def downgrade():
    op.drop_index('ix_alert_status', table_name='conversation_alert_intents')
    for table in ('conversation_alert_intents', 'conversation_receipts', 'conversation_send_intents',
                  'conversation_control_audit', 'conversation_controls'):
        op.drop_table(table)
