import asyncio
import logging
from pathlib import Path

from apexrep.config import Settings, get_settings
from apexrep.db import Connection, connect

logger = logging.getLogger("apexrep.migrate")


def pending_migrations(migrations_dir: Path, applied: set[str]) -> list[Path]:
    return [path for path in sorted(migrations_dir.glob("*.sql")) if path.name not in applied]


async def apply_migrations(conn: Connection, migrations_dir: Path) -> list[str]:
    await conn.execute(
        """
        create table if not exists schema_migrations (
          version    text primary key,
          applied_at timestamptz not null default now()
        )
        """
    )
    rows = await conn.fetch("select version from schema_migrations")
    applied: set[str] = {row["version"] for row in rows}

    newly_applied: list[str] = []
    for path in pending_migrations(migrations_dir, applied):
        async with conn.transaction():
            await conn.execute(path.read_text(encoding="utf-8"))
            await conn.execute("insert into schema_migrations (version) values ($1)", path.name)
        logger.info("applied %s", path.name)
        newly_applied.append(path.name)
    return newly_applied


async def run(settings: Settings) -> None:
    conn = await connect(settings)
    try:
        applied = await apply_migrations(conn, settings.migrations_dir)
    finally:
        await conn.close()
    logger.info("migrations up to date (%d applied)", len(applied))


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    asyncio.run(run(get_settings()))


if __name__ == "__main__":
    main()
