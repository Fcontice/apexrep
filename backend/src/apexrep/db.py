from typing import TYPE_CHECKING
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import asyncpg

from apexrep.config import Settings

if TYPE_CHECKING:
    Pool = asyncpg.Pool[asyncpg.Record]
    Connection = asyncpg.Connection[asyncpg.Record]
else:
    Pool = asyncpg.Pool
    Connection = asyncpg.Connection

# Neon's pooled connection string is PgBouncer in transaction mode, which cannot
# keep prepared statements, so the statement cache stays off everywhere.
STATEMENT_CACHE_SIZE: int = 0

# libpq options that asyncpg does not know and would send to the server as
# settings, failing the connection. Neon's connection strings include the first.
_UNSUPPORTED_DSN_PARAMS: frozenset[str] = frozenset({"channel_binding"})


def asyncpg_dsn(database_url: str) -> str:
    """Make a connection string copied from Neon usable by asyncpg."""
    parts = urlsplit(database_url)
    kept = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if key not in _UNSUPPORTED_DSN_PARAMS
    ]
    return urlunsplit(parts._replace(query=urlencode(kept)))


async def create_pool(settings: Settings) -> Pool:
    return await asyncpg.create_pool(
        dsn=asyncpg_dsn(settings.database_url),
        min_size=settings.db_pool_min_size,
        max_size=settings.db_pool_max_size,
        statement_cache_size=STATEMENT_CACHE_SIZE,
    )


async def connect(settings: Settings) -> Connection:
    return await asyncpg.connect(
        dsn=asyncpg_dsn(settings.database_url),
        statement_cache_size=STATEMENT_CACHE_SIZE,
    )
