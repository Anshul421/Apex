from __future__ import annotations

from contextlib import asynccontextmanager
from fastapi import FastAPI

from app.api.routes import router
from app.config import get_settings
from app.observability import configure_observability
from app.storage.database import Base, engine

# Import models before create_all in development.
from app.storage import models as _models  # noqa: F401

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Tests and SQLite-only local sandboxes may create tables directly.
    # PostgreSQL development/production schema changes go through Alembic.
    if settings.environment == 'test' or (
        settings.environment == 'development'
        and settings.database_url.startswith('sqlite')
    ):
        Base.metadata.create_all(engine)
    yield


app = FastAPI(
    title=settings.app_name,
    version='0.1.0',
    description='Constraint-verified autonomous athlete operations backend.',
    lifespan=lifespan,
)
configure_observability(app, settings.log_level)
app.include_router(router, prefix=settings.api_prefix)
