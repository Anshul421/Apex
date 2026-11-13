"""ML experiment tracking and model registry

Revision ID: 9f4c2a71d8b0
Revises: 5715ee520648
Create Date: 2026-09-13 16:20:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '9f4c2a71d8b0'
down_revision: Union[str, Sequence[str], None] = '5715ee520648'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'ml_experiments',
        sa.Column('id', sa.String(length=64), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name'),
    )

    op.create_table(
        'ml_runs',
        sa.Column('id', sa.String(length=64), nullable=False),
        sa.Column('experiment_id', sa.String(length=64), nullable=False),
        sa.Column('run_name', sa.String(length=255), nullable=False),
        sa.Column('status', sa.String(length=32), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('ended_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('code_version', sa.String(length=128), nullable=False),
        sa.Column('dataset_name', sa.String(length=255), nullable=False),
        sa.Column('dataset_version', sa.String(length=128), nullable=False),
        sa.Column('dataset_sha256', sa.String(length=64), nullable=False),
        sa.Column('feature_schema_version', sa.String(length=128), nullable=False),
        sa.Column('random_seed', sa.Integer(), nullable=False),
        sa.Column('params', sa.JSON(), nullable=False),
        sa.Column('metrics', sa.JSON(), nullable=False),
        sa.Column('tags', sa.JSON(), nullable=False),
        sa.Column('artifact_uri', sa.Text(), nullable=True),
        sa.Column('selected_model', sa.String(length=128), nullable=True),
        sa.Column('decision', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['experiment_id'], ['ml_experiments.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_ml_runs_experiment_id'), 'ml_runs', ['experiment_id'], unique=False)
    op.create_index(op.f('ix_ml_runs_status'), 'ml_runs', ['status'], unique=False)
    op.create_index('ix_ml_runs_experiment_started', 'ml_runs', ['experiment_id', 'started_at'], unique=False)

    op.create_table(
        'ml_model_versions',
        sa.Column('id', sa.String(length=64), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('run_id', sa.String(length=64), nullable=False),
        sa.Column('stage', sa.String(length=32), nullable=False),
        sa.Column('alias', sa.String(length=64), nullable=True),
        sa.Column('artifact_uri', sa.Text(), nullable=False),
        sa.Column('model_format', sa.String(length=64), nullable=False),
        sa.Column('input_schema', sa.JSON(), nullable=False),
        sa.Column('metrics', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['run_id'], ['ml_runs.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name', 'version', name='uq_ml_model_name_version'),
        sa.UniqueConstraint('name', 'alias', name='uq_ml_model_name_alias'),
    )
    op.create_index(op.f('ix_ml_model_versions_alias'), 'ml_model_versions', ['alias'], unique=False)
    op.create_index(op.f('ix_ml_model_versions_name'), 'ml_model_versions', ['name'], unique=False)
    op.create_index(op.f('ix_ml_model_versions_run_id'), 'ml_model_versions', ['run_id'], unique=False)
    op.create_index(op.f('ix_ml_model_versions_stage'), 'ml_model_versions', ['stage'], unique=False)
    op.create_index('ix_ml_model_versions_name_created', 'ml_model_versions', ['name', 'created_at'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_ml_model_versions_name_created', table_name='ml_model_versions')
    op.drop_index(op.f('ix_ml_model_versions_stage'), table_name='ml_model_versions')
    op.drop_index(op.f('ix_ml_model_versions_run_id'), table_name='ml_model_versions')
    op.drop_index(op.f('ix_ml_model_versions_name'), table_name='ml_model_versions')
    op.drop_index(op.f('ix_ml_model_versions_alias'), table_name='ml_model_versions')
    op.drop_table('ml_model_versions')

    op.drop_index('ix_ml_runs_experiment_started', table_name='ml_runs')
    op.drop_index(op.f('ix_ml_runs_status'), table_name='ml_runs')
    op.drop_index(op.f('ix_ml_runs_experiment_id'), table_name='ml_runs')
    op.drop_table('ml_runs')

    op.drop_table('ml_experiments')
