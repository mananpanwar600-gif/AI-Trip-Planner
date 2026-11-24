import logging
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from backend.app.config import get_settings
from backend.app.utils.exceptions import DatabaseUnavailable

logger = logging.getLogger(__name__)


def _database_path() -> str:
    database_url = get_settings().database_url
    prefixes = ("sqlite+aiosqlite:///", "sqlite:///")
    for prefix in prefixes:
        if database_url.startswith(prefix):
            path = database_url[len(prefix) :]
            if not path or path == ":memory:":
                raise DatabaseUnavailable(
                    "Configure a file-backed SQLite DATABASE_URL."
                )
            database_path = Path(path)
            if not database_path.is_absolute():
                database_path = Path.cwd() / database_path
            database_path.parent.mkdir(parents=True, exist_ok=True)
            return str(database_path)
    raise DatabaseUnavailable(
        "This application currently supports SQLite DATABASE_URL values only."
    )


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    try:
        with sqlite3.connect(_database_path(), timeout=10) as connection:
            connection.row_factory = sqlite3.Row
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS trips (
                    trip_id TEXT PRIMARY KEY,
                    destination TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    request_json TEXT NOT NULL,
                    plan_json TEXT NOT NULL
                )
                """
            )
            yield connection
    except sqlite3.Error as exc:
        logger.exception("Could not use the local trip database.")
        raise DatabaseUnavailable(
            "The local trip database is unavailable."
        ) from exc


def initialize_database() -> None:
    with connect():
        return