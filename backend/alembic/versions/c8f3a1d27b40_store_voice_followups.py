"""Vendedor ativo: registro de respostas por voz (store_voice_sends) e acompanhamentos comerciais (store_followups).

Duas tabelas NOVAS (não existem em produção). A migração só cria; o downgrade só remove tabela vazia e recusa quando houver
linhas (histórico de envios é evidência: não se apaga por reversão automática).

ATENÇÃO (cadeia): `down_revision = 'e610080003'` é a cabeça da cadeia DESTE repositório. A cadeia de produção termina em
`9e2f1c6d7a80` e as revisões e610080001..3 deste repositório ainda dependem de decisão/confirmação (ver SESSION_TRACKING.md).
Antes de qualquer implantação, confirme a cabeça instalada e reaponte `down_revision` se necessário — sem `stamp`.

Revision ID: c8f3a1d27b40
Revises: e610080003
"""
import alembic.op as op
import sqlalchemy as sa

revision = "c8f3a1d27b40"
down_revision = "e610080003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "store_voice_sends",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("dedupe_key", sa.String(120), nullable=False),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("contact_id", sa.Integer(), sa.ForeignKey("contacts.id"), nullable=False),
        sa.Column("instance", sa.String(64), nullable=False),
        sa.Column("source_message_id", sa.Integer(), sa.ForeignKey("messages.id")),
        sa.Column("followup_id", sa.Integer()),
        sa.Column("status", sa.String(24), nullable=False, server_default="queued"),
        sa.Column("reason", sa.Text()),
        sa.Column("script_text", sa.Text(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("audio_sha256", sa.String(64)),
        sa.Column("audio_seconds", sa.Float()),
        sa.Column("audio_bytes", sa.Integer()),
        sa.Column("engine", sa.String(32)),
        sa.Column("model_revision", sa.String(64)),
        sa.Column("reference_sha256", sa.String(64)),
        sa.Column("receipt_id", sa.String(128)),
        sa.Column("sent_at", sa.DateTime(timezone=True)),
        sa.Column("history", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("dedupe_key", name="uq_store_voice_sends_dedupe_key"),
    )
    op.create_index("ix_store_voice_sends_contact_id", "store_voice_sends", ["contact_id"])
    op.create_index("ix_store_voice_sends_source_message_id", "store_voice_sends", ["source_message_id"])
    op.create_index("ix_store_voice_sends_followup_id", "store_voice_sends", ["followup_id"])
    op.create_index("ix_store_voice_sends_status", "store_voice_sends", ["status"])

    op.create_table(
        "store_followups",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("dedupe_key", sa.String(120), nullable=False),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("contact_id", sa.Integer(), sa.ForeignKey("contacts.id"), nullable=False),
        sa.Column("customer_id", sa.Integer(), sa.ForeignKey("store_customers.id"), nullable=False),
        sa.Column("instance", sa.String(64), nullable=False),
        sa.Column("origin_type", sa.String(32), nullable=False),
        sa.Column("origin_id", sa.String(64), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="scheduled"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("cancel_reason", sa.Text()),
        sa.Column("job_id", sa.Integer()),
        sa.Column("sent_at", sa.DateTime(timezone=True)),
        sa.Column("history", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("dedupe_key", name="uq_store_followups_dedupe_key"),
    )
    op.create_index("ix_store_followups_contact_id", "store_followups", ["contact_id"])
    op.create_index("ix_store_followups_customer_id", "store_followups", ["customer_id"])
    op.create_index("ix_store_followups_status_due_at", "store_followups", ["status", "due_at"])


def downgrade() -> None:
    bind = op.get_bind()
    for table in ("store_followups", "store_voice_sends"):
        if bind.execute(sa.text(f"SELECT count(*) FROM {table}")).scalar():
            raise RuntimeError(f"Recusado: {table} contém histórico de envios; exporte e remova manualmente se for o caso.")
    op.drop_table("store_followups")
    op.drop_table("store_voice_sends")
