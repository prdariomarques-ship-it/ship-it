"""create goals and goal_dependencies tables

Revision ID: 23cd00e69ae5
Revises: 86ec0249ba12
Create Date: 2026-07-16 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '23cd00e69ae5'
down_revision: Union[str, None] = '86ec0249ba12'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Same reasoning as 790826c45a84_initial_schema.py's _ENUM_NAMES: op.drop_table
# alone never emits DROP TYPE, so these two enum types must be dropped
# explicitly in downgrade() or they'd collide with CREATE TYPE on the next upgrade.
_ENUM_NAMES = ('goalstatus', 'goalpriority')


def upgrade() -> None:
    op.create_table(
        'goals',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column(
            'status',
            sa.Enum('AWAITING_APPROVAL', 'PENDING', 'IN_PROGRESS', 'COMPLETED', 'CANCELLED', name='goalstatus'),
            nullable=False,
        ),
        sa.Column(
            'priority',
            sa.Enum('LOW', 'MEDIUM', 'HIGH', 'URGENT', name='goalpriority'),
            nullable=False,
        ),
        sa.Column('deadline', sa.DateTime(timezone=True), nullable=True),
        sa.Column('progress_percent', sa.Integer(), nullable=False),
        sa.Column('requires_approval', sa.Boolean(), nullable=False),
        sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('approved_by_id', sa.Integer(), nullable=True),
        sa.Column('recurrence_interval_days', sa.Integer(), nullable=True),
        sa.Column('recurrence_parent_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['approved_by_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['recurrence_parent_id'], ['goals.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_goals_user_id'), 'goals', ['user_id'], unique=False)
    op.create_index(op.f('ix_goals_status'), 'goals', ['status'], unique=False)
    op.create_index(op.f('ix_goals_deadline'), 'goals', ['deadline'], unique=False)
    op.create_index(op.f('ix_goals_recurrence_parent_id'), 'goals', ['recurrence_parent_id'], unique=False)

    op.create_table(
        'goal_dependencies',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('goal_id', sa.Integer(), nullable=False),
        sa.Column('depends_on_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['goal_id'], ['goals.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['depends_on_id'], ['goals.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('goal_id', 'depends_on_id', name='uq_goal_dependency'),
    )
    op.create_index(op.f('ix_goal_dependencies_goal_id'), 'goal_dependencies', ['goal_id'], unique=False)
    op.create_index(
        op.f('ix_goal_dependencies_depends_on_id'), 'goal_dependencies', ['depends_on_id'], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_goal_dependencies_depends_on_id'), table_name='goal_dependencies')
    op.drop_index(op.f('ix_goal_dependencies_goal_id'), table_name='goal_dependencies')
    op.drop_table('goal_dependencies')

    op.drop_index(op.f('ix_goals_recurrence_parent_id'), table_name='goals')
    op.drop_index(op.f('ix_goals_deadline'), table_name='goals')
    op.drop_index(op.f('ix_goals_status'), table_name='goals')
    op.drop_index(op.f('ix_goals_user_id'), table_name='goals')
    op.drop_table('goals')

    for enum_name in _ENUM_NAMES:
        sa.Enum(name=enum_name).drop(op.get_bind(), checkfirst=True)
