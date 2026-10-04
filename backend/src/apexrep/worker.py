import asyncio
import contextlib
import logging
import signal

import asyncpg

from apexrep.config import Settings, get_settings
from apexrep.db import Pool, create_pool
from apexrep.heartbeat import write_heartbeat

logger = logging.getLogger("apexrep.worker")


async def run_loop(pool: Pool, settings: Settings, stop: asyncio.Event) -> None:
    while not stop.is_set():
        try:
            await write_heartbeat(pool)
        except (asyncpg.PostgresError, asyncpg.InterfaceError, OSError):
            logger.exception("heartbeat write failed")
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=settings.worker_loop_interval_s)


async def run(settings: Settings) -> None:
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    # Signal handlers are not available on the Windows event loop; Ctrl+C still
    # stops the worker there through KeyboardInterrupt.
    with contextlib.suppress(NotImplementedError):
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, stop.set)

    pool = await create_pool(settings)
    logger.info("worker started, loop interval %ss", settings.worker_loop_interval_s)
    try:
        await run_loop(pool, settings, stop)
    finally:
        await pool.close()
        logger.info("worker stopped")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(run(get_settings()))


if __name__ == "__main__":
    main()
