from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateIndex, CreateTable

from app.storage.database import Base
from app.storage import models as _models  # noqa: F401


def main() -> None:
    dialect = postgresql.dialect()
    statements: list[str] = []
    for table in Base.metadata.sorted_tables:
        statements.append(str(CreateTable(table).compile(dialect=dialect)).strip() + ';')
    for table in Base.metadata.sorted_tables:
        for index in sorted(table.indexes, key=lambda item: item.name or ''):
            statements.append(str(CreateIndex(index).compile(dialect=dialect)).strip() + ';')
    Path('POSTGRES_SCHEMA.sql').write_text('\n\n'.join(statements) + '\n')


if __name__ == '__main__':
    main()
