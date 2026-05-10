import logging
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import delete

from app.database import AsyncSessionLocal
from app.models.devis import Devis

logger = logging.getLogger(__name__)
scheduler = AsyncIOScheduler(timezone="UTC")


async def _delete_old_devis() -> None:
    cutoff = datetime.now(timezone.utc) - timedelta(days=365)
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            delete(Devis).where(Devis.created_at < cutoff)
        )
        await session.commit()
        logger.info("RGPD cleanup: deleted %d devis older than 12 months", result.rowcount)


def start_scheduler() -> None:
    scheduler.add_job(_delete_old_devis, "cron", hour=3, minute=0, id="rgpd_cleanup")
    scheduler.start()
    logger.info("APScheduler started")


def stop_scheduler() -> None:
    scheduler.shutdown(wait=False)
    logger.info("APScheduler stopped")
