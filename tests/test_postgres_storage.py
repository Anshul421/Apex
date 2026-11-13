from __future__ import annotations

from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateIndex, CreateTable

from app.config import Settings
from app.storage.database import Base
from app.storage.models import MLExperiment, MLModelVersion, MLRun


def test_postgres_urls_are_normalized_to_psycopg():
    cfg = Settings(_env_file=None, database_url='postgresql://user:pass@localhost:5432/apex')
    assert cfg.database_url == 'postgresql+psycopg://user:pass@localhost:5432/apex'

    cfg2 = Settings(_env_file=None, database_url='postgres://user:pass@localhost:5432/apex')
    assert cfg2.database_url == 'postgresql+psycopg://user:pass@localhost:5432/apex'


def test_ml_tracking_schema_compiles_for_postgresql():
    dialect = postgresql.dialect()
    for table in (MLExperiment.__table__, MLRun.__table__, MLModelVersion.__table__):
        ddl = str(CreateTable(table).compile(dialect=dialect))
        assert 'CREATE TABLE' in ddl
        assert table.name in ddl

    index_ddls = [
        str(CreateIndex(index).compile(dialect=dialect))
        for table in Base.metadata.tables.values()
        for index in table.indexes
        if table.name in {'ml_runs', 'ml_model_versions'}
    ]
    assert any('ix_ml_runs_experiment_started' in ddl for ddl in index_ddls)
    assert any('ix_ml_model_versions_name_created' in ddl for ddl in index_ddls)
