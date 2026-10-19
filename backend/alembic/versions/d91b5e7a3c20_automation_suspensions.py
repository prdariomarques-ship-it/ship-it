"""Suspensao da automacao de WhatsApp: tabela atomica (uma linha por escopo).

Substitui a lista separada por virgula em app_settings (read-modify-write sujeito a corrida) por uma linha por escopo
(`global` ou `instance:<nome>`), com a chave primaria como arbitro.

ATENCAO (cadeia): `down_revision = 'c8f3a1d27b40'` e a cabeca da cadeia DESTE repositorio (ver o aviso de cadeia na
migracao c8f3a1d27b40). Confirme a cabeca instalada antes de qualquer implantacao -- sem `stamp`.
O downgrade recusa quando houver suspensoes ativas (estado operacional: nao se apaga por reversao automatica).

Revision ID: d91b5e7a3c20
Revises: c8f3a1d27b40
"""
import alembic.op as op
import sqlalchemy as sa

revision = "d91b5e7a3c20"
down_revision = "c8f3a1d27b40"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "automation_suspensions",
        sa.Column("scope", sa.String(80), primary_key=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("actor_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.execute(sa.text("SELECT count(*) FROM automation_suspensions")).scalar():
        raise RuntimeError("Recusado: ha suspensoes de automacao ativas; retome-as antes de reverter.")
    op.drop_table("automation_suspensions")
