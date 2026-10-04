from typing import TYPE_CHECKING

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


async def create_pool(settings: Settings) -> Pool:
    return await asyncpg.create_pool(
        dsn=settings.database_url,
        min_size=settings.db_pool_min_size,
        max_size=settings.db_pool_max_size,
        statement_cache_size=STATEMENT_CACHE_SIZE,
    )


async def connect(settings: Settings) -> Connection:
    return await asyncpg.connect(
        dsn=settings.database_url,
        statement_cache_size=STATEMENT_CACHE_SIZE,
    )
