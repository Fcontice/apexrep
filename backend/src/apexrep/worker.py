import asyncio
import contextlib
import logging
import signal

import asyncpg

from apexrep.als.client import build_als_client
from apexrep.config import Settings, get_settings
from apexrep.db import Pool, create_pool
from apexrep.heartbeat import write_heartbeat
from apexrep.players.poller import Poller, PollSummary

logger = logging.getLogger("apexrep.worker")


def _log_summary(summary: PollSummary) -> None:
    if summary == PollSummary():
        return
    logger.info("poll run: %s", summary.model_dump_json(exclude_defaults=True))


async def run_loop(pool: Pool, poller: Poller, settings: Settings, stop: asyncio.Event) -> None:
    while not stop.is_set():
        try:
            await write_heartbeat(pool)
            _log_summary(await poller.run_once())
        except (asyncpg.PostgresError, asyncpg.InterfaceError, OSError):
            logger.exception("worker loop iteration failed")
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
    als = build_als_client(settings, rate_per_s=settings.als_rate_worker_per_s)
    poller = Poller(pool=pool, als=als, settings=settings)
    logger.info("worker started, loop interval %ss", settings.worker_loop_interval_s)
    try:
        await run_loop(pool, poller, settings, stop)
    finally:
        await als.aclose()
        await pool.close()
        logger.info("worker stopped")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    # httpx logs every request URL at INFO; keep the worker log to poll summaries.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(run(get_settings()))


if __name__ == "__main__":
    main()
