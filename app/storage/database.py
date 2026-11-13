from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    pass


_settings = get_settings()
_is_sqlite = _settings.database_url.startswith('sqlite')

_engine_kwargs: dict = {
    'pool_pre_ping': True,
    'future': True,
}

if _is_sqlite:
    _engine_kwargs['connect_args'] = {'check_same_thread': False}
else:
    _engine_kwargs.update(
        pool_size=_settings.db_pool_size,
        max_overflow=_settings.db_max_overflow,
        pool_recycle=_settings.db_pool_recycle_seconds,
    )

engine = create_engine(
    _settings.database_url,
    **_engine_kwargs,
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    expire_on_commit=False,
    class_=Session,
)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
