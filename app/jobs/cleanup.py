import logging
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import and_, delete, exists, select

from app.database import AsyncSessionLocal
from app.models.attribution import Visitor
from app.models.billing import Customer
from app.models.devis import Devis
from app.models.lead import Lead

logger = logging.getLogger(__name__)
scheduler = AsyncIOScheduler(timezone="UTC")

RETENTION_DAYS = 365
# Durée de vie max. du cookie affra_vid (13 mois, recommandation CNIL) : au-delà, l'identifiant ne revient plus.
VISITOR_RETENTION_DAYS = 395


async def purge_expired_data(session) -> dict[str, int]:
    """Purge RGPD. Ne touche jamais aux leads devenus clients (factures = obligation comptable)."""
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=RETENTION_DAYS)

    devis_result = await session.execute(delete(Devis).where(Devis.created_at < cutoff))

    leads_result = await session.execute(
        delete(Lead).where(
            Lead.created_at < cutoff,
            Lead.updated_at < cutoff,
            ~exists(select(Customer.id).where(Customer.lead_id == Lead.id)),
            ~exists(select(Devis.id).where(and_(Devis.lead_id == Lead.id, Devis.created_at >= cutoff))),
        )
    )

    visitors_result = await session.execute(
        delete(Visitor).where(
            Visitor.last_seen_at < now - timedelta(days=VISITOR_RETENTION_DAYS),
            ~exists(select(Lead.id).where(Lead.visitor_id == Visitor.id)),
        )
    )
    return {"devis": devis_result.rowcount, "leads": leads_result.rowcount, "visitors": visitors_result.rowcount}


async def _delete_old_devis() -> None:
    async with AsyncSessionLocal() as session:
        counts = await purge_expired_data(session)
        await session.commit()
        logger.info(
            "RGPD cleanup: deleted %d devis, %d leads (non clients), %d visitors older than retention",
            counts["devis"], counts["leads"], counts["visitors"],
        )


def start_scheduler() -> None:
    scheduler.add_job(_delete_old_devis, "cron", hour=3, minute=0, id="rgpd_cleanup")
    scheduler.start()
    logger.info("APScheduler started")


def stop_scheduler() -> None:
    scheduler.shutdown(wait=False)
    logger.info("APScheduler stopped")
