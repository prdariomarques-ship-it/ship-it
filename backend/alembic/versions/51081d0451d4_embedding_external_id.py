"""Add embeddings.external_id -- lets a caller re-embed or drop the vector for
an external thing (e.g. a Product.sku) without first looking up its internal
Embedding.id. First consumer: product-catalog semantic search -- see
memory/service.py::replace_by_external_id / delete_by_external_id."""

from alembic import op
import sqlalchemy as sa

revision = "51081d0451d4"
down_revision = "c91d5e7a3b20"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "embeddings", sa.Column("external_id", sa.String(length=255), nullable=True)
    )
    op.create_index(op.f("ix_embeddings_external_id"), "embeddings", ["external_id"])


def downgrade():
    op.drop_index(op.f("ix_embeddings_external_id"), table_name="embeddings")
    op.drop_column("embeddings", "external_id")
