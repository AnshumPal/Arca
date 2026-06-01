"""
scheduler.py
APScheduler setup for the nightly optimizer run.
Runs at 02:00 UTC every day — low-traffic window.
"""

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.database import AsyncSessionLocal

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


async def nightly_optimizer_job() -> None:
    """Runs the optimizer cycle with its own DB session."""
    # Import here to avoid circular imports at module load time
    from app.optimizer import run_optimizer_cycle

    logger.info("Nightly optimizer job starting")
    try:
        async with AsyncSessionLocal() as db:
            await run_optimizer_cycle(db, triggered_by="schedule")
        logger.info("Nightly optimizer job completed")
    except Exception as exc:
        logger.error("Nightly optimizer job failed: %s", exc)


def start_scheduler() -> None:
    scheduler.add_job(
        nightly_optimizer_job,
        CronTrigger(hour=2, minute=0),   # 02:00 UTC daily
        id="nightly_optimizer",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("Scheduler started — nightly optimizer at 02:00 UTC")


def stop_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")
