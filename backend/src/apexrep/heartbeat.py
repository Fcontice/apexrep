from datetime import datetime

from apexrep.db import Pool


async def write_heartbeat(pool: Pool) -> None:
    await pool.execute(
        """
        insert into worker_heartbeat (id, beat_at)
        values (1, now())
        on conflict (id) do update set beat_at = excluded.beat_at
        """
    )


async def fetch_heartbeat(pool: Pool) -> datetime | None:
    beat_at: datetime | None = await pool.fetchval(
        "select beat_at from worker_heartbeat where id = 1"
    )
    return beat_at
