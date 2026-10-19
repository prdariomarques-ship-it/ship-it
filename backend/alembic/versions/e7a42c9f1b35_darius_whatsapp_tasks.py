"""Vinculo mensagem WhatsApp -> tarefa DARIUS (trilha de auditoria + barreira de deduplicacao).

Tabela NOVA. Nao armazena texto de mensagem nem de resposta (somente ids, tamanho e hash).
O downgrade recusa quando houver linhas (historico de atendimento e evidencia; nao se apaga por reversao automatica).

ATENCAO (cadeia): `down_revision = 'd91b5e7a3c20'` e a cabeca da cadeia DESTE repositorio
(ver o aviso de cadeia em c8f3a1d27b40).

Revision ID: e7a42c9f1b35
Revises: d91b5e7a3c20
"""
import alembic.op as op
import sqlalchemy as sa

revision = "e7a42c9f1b35"
down_revision = "d91b5e7a3c20"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "darius_whatsapp_tasks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("dedupe_key", sa.String(64), nullable=False),
        sa.Column("message_id", sa.Integer(), sa.ForeignKey("messages.id"), nullable=False),
        sa.Column("contact_id", sa.Integer(), sa.ForeignKey("contacts.id"), nullable=False),
        sa.Column("instance", sa.String(128), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("darius_task_id", sa.String(128)),
        sa.Column("darius_status", sa.String(16)),
        sa.Column("control_revision", sa.Integer()),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text()),
        sa.Column("reply_job_id", sa.Integer()),
        sa.Column("reply_chars", sa.Integer()),
        sa.Column("reply_sha256", sa.String(64)),
        sa.Column("history", sa.JSON(), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("dedupe_key", name="uq_darius_whatsapp_tasks_dedupe_key"),
    )
    op.create_index("ix_darius_whatsapp_tasks_message_id", "darius_whatsapp_tasks", ["message_id"])
    op.create_index("ix_darius_whatsapp_tasks_contact_id", "darius_whatsapp_tasks", ["contact_id"])
    op.create_index("ix_darius_whatsapp_tasks_status", "darius_whatsapp_tasks", ["status"])
    op.create_index("ix_darius_whatsapp_tasks_status_created", "darius_whatsapp_tasks", ["status", "created_at"])


def downgrade() -> None:
    bind = op.get_bind()
    if bind.execute(sa.text("SELECT count(*) FROM darius_whatsapp_tasks")).scalar():
        raise RuntimeError(
            "Recusado: darius_whatsapp_tasks contem historico de atendimento; exporte e remova manualmente."
        )
    op.drop_table("darius_whatsapp_tasks")
