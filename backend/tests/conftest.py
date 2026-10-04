import json
import os
from collections.abc import AsyncIterator
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import asyncpg
import pytest
from pydantic import JsonValue

from apexrep.config import REPO_ROOT
from apexrep.db import STATEMENT_CACHE_SIZE, Pool
from apexrep.migrate import apply_migrations

FIXTURES_DIR: Path = Path(__file__).parent / "fixtures" / "als"

# Integration tests run against the Docker Postgres (`docker compose up -d db`),
# in a separate database so they never touch development data.
TEST_DATABASE_URL: str = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://apexrep:apexrep@localhost:5433/apexrep_test"
)


def load_fixture(name: str) -> JsonValue:
    body: JsonValue = json.loads((FIXTURES_DIR / name).read_text(encoding="utf-8"))
    return body


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


async def _ensure_test_database() -> None:
    parts = urlsplit(TEST_DATABASE_URL)
    database = parts.path.lstrip("/")
    admin_url = urlunsplit(parts._replace(path="/postgres"))
    admin = await asyncpg.connect(admin_url, timeout=3)
    try:
        exists = await admin.fetchval("select 1 from pg_database where datname = $1", database)
        if not exists:
            await admin.execute(f'create database "{database}"')
    finally:
        await admin.close()


@pytest.fixture
async def pool(anyio_backend: str) -> AsyncIterator[Pool]:
    """A pool on a migrated, emptied test database. Skips if Postgres is not running."""
    try:
        await _ensure_test_database()
    except (OSError, TimeoutError, asyncpg.PostgresError) as exc:
        pytest.skip(f"test database not reachable: {exc!r}")

    conn = await asyncpg.connect(TEST_DATABASE_URL, statement_cache_size=STATEMENT_CACHE_SIZE)
    try:
        await apply_migrations(conn, REPO_ROOT / "migrations")
        await conn.execute(
            "truncate matches, snapshots, player_aliases, players, worker_heartbeat "
            "restart identity cascade"
        )
    finally:
        await conn.close()

    test_pool = await asyncpg.create_pool(
        TEST_DATABASE_URL, min_size=1, max_size=5, statement_cache_size=STATEMENT_CACHE_SIZE
    )
    try:
        yield test_pool
    finally:
        await test_pool.close()
