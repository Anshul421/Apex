from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


def _checkpoint_path() -> Path:
    raw = os.getenv(
        "LANGGRAPH_CHECKPOINT_DB",
        "./langgraph_checkpoints.sqlite",
    )

    path = Path(raw).expanduser()

    if not path.is_absolute():
        path = Path.cwd() / path

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    return path


@contextmanager
def sqlite_checkpointer() -> Iterator[object]:
    """
    Durable local LangGraph checkpointer.

    Good for:
        local development
        demos
        very small deployments

    Later production upgrade:
        langgraph-checkpoint-postgres
    """

    try:
        from langgraph.checkpoint.sqlite import SqliteSaver
    except ImportError as exc:
        raise RuntimeError(
            "Missing LangGraph SQLite checkpoint package. "
            "Install it with: "
            "pip install langgraph-checkpoint-sqlite"
        ) from exc

    # Current checkpoint packages support strict msgpack mode.
    # Our graph state is intentionally JSON-like as well.
    os.environ.setdefault(
        "LANGGRAPH_STRICT_MSGPACK",
        "true",
    )

    connection = sqlite3.connect(
        str(_checkpoint_path()),
        check_same_thread=False,
    )

    try:
        saver = SqliteSaver(connection)

        yield saver

    finally:
        connection.close()