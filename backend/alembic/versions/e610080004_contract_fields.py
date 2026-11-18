"""Add the persistent fields required by product indexing and Twin pause state.

This forward migration belongs to the PR branch. The repository's historical
baseline is still unverified; do not apply the branch migration chain to the
production database until its actual Alembic ancestry has been recovered.
Existing columns/indexes are preserved and only objects created by this
migration are eligible for downgrade.
"""
from alembic import op
import sqlalchemy as sa

revision = "e610080004"
down_revision = "e610080003"
branch_labels = None
depends_on = None

_MARKER_TABLE = "_mig_e610080004_created_objects"
_INDEX_NAME = "ix_embeddings_external_id"
_COLUMN_OBJECTS = (
    ("contacts", "awaiting_reply_since"),
    ("embeddings", "external_id"),
)
_INDEX_OBJECT = f"index:embeddings.{_INDEX_NAME}"


def _ensure_marker_table(bind) -> None:
    if not sa.inspect(bind).has_table(_MARKER_TABLE):
        op.create_table(
            _MARKER_TABLE,
            sa.Column("object_name", sa.String(128), primary_key=True),
            sa.Column(
                "created_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.func.now(),
            ),
        )


def _record_created(bind, object_name: str) -> None:
    bind.execute(
        sa.text(f'INSERT INTO "{_MARKER_TABLE}" (object_name) VALUES (:name)'),
        {"name": object_name},
    )


def _column_exists(bind, table: str, column: str) -> bool:
    inspector = sa.inspect(bind)
    if not inspector.has_table(table):
        raise RuntimeError(
            f"Refusing to migrate contract fields: expected table {table!r} is absent"
        )
    return column in {item["name"] for item in inspector.get_columns(table)}


def _index_columns(bind) -> list[str] | None:
    inspector = sa.inspect(bind)
    if not inspector.has_table("embeddings"):
        return None
    for index in inspector.get_indexes("embeddings"):
        if index["name"] == _INDEX_NAME:
            return list(index.get("column_names") or [])
    return None


def upgrade() -> None:
    bind = op.get_bind()
    _ensure_marker_table(bind)

    for table, column in _COLUMN_OBJECTS:
        if _column_exists(bind, table, column):
            continue
        if table == "contacts":
            op.add_column(
                table, sa.Column(column, sa.DateTime(timezone=True), nullable=True)
            )
        else:
            op.add_column(
                table, sa.Column(column, sa.String(length=255), nullable=True)
            )
        _record_created(bind, f"column:{table}.{column}")

    index_columns = _index_columns(bind)
    if index_columns is not None:
        if index_columns != ["external_id"]:
            raise RuntimeError(
                f"Refusing to reuse {_INDEX_NAME}: it exists on {index_columns!r}"
            )
    else:
        if not _column_exists(bind, "embeddings", "external_id"):
            raise RuntimeError("Cannot index embeddings.external_id before it exists")
        op.create_index(_INDEX_NAME, "embeddings", ["external_id"])
        _record_created(bind, _INDEX_OBJECT)


def _has_non_null_value(bind, table: str, column: str) -> bool:
    statement = sa.text(
        f'SELECT 1 FROM "{table}" WHERE "{column}" IS NOT NULL LIMIT 1'
    )
    return bind.execute(statement).first() is not None


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    has_marker = inspector.has_table(_MARKER_TABLE)
    present_columns = {
        f"column:{table}.{column}"
        for table, column in _COLUMN_OBJECTS
        if inspector.has_table(table)
        and column in {item["name"] for item in inspector.get_columns(table)}
    }
    index_present = _index_columns(bind) is not None

    if not has_marker:
        if present_columns or index_present:
            raise RuntimeError(
                "Refusing to downgrade e610080004: contract fields/index exist "
                "without this migration's ownership record"
            )
        return

    owned = {
        row[0]
        for row in bind.execute(
            sa.text(f'SELECT object_name FROM "{_MARKER_TABLE}"')
        )
    }
    columns_to_drop: dict[str, list[str]] = {}
    blocked: list[str] = []

    for table, column in _COLUMN_OBJECTS:
        object_name = f"column:{table}.{column}"
        if object_name not in owned or object_name not in present_columns:
            continue
        if _has_non_null_value(bind, table, column):
            blocked.append(object_name)
        else:
            columns_to_drop.setdefault(table, []).append(column)

    index_owned = _INDEX_OBJECT in owned and index_present
    external_id_owned = "column:embeddings.external_id" in owned
    if external_id_owned and index_present and not index_owned:
        blocked.append("embeddings.external_id (coupled to a foreign index)")

    if blocked:
        raise RuntimeError(
            "Refusing to downgrade e610080004 because it would remove data or "
            "an index this migration does not own: " + ", ".join(blocked)
        )

    if index_owned:
        op.drop_index(_INDEX_NAME, table_name="embeddings")

    for table, columns in columns_to_drop.items():
        with op.batch_alter_table(table) as batch:
            for column in columns:
                batch.drop_column(column)

    for object_name in owned:
        bind.execute(
            sa.text(
                f'DELETE FROM "{_MARKER_TABLE}" WHERE object_name = :name'
            ),
            {"name": object_name},
        )
    if bind.execute(sa.text(f'SELECT 1 FROM "{_MARKER_TABLE}" LIMIT 1')).first() is None:
        op.drop_table(_MARKER_TABLE)
