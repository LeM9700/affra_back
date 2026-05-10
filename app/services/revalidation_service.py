import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


async def trigger_revalidation(path: str) -> None:
    """
    Envoie un webhook de revalidation ISR à Next.js après une mutation de contenu.
    Ne bloque pas le flux principal en cas d'échec.
    """
    if not settings.nextjs_revalidate_url:
        logger.debug("NEXTJS_REVALIDATE_URL not set — skipping ISR revalidation for %s", path)
        return

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(
                settings.nextjs_revalidate_url,
                json={"path": path},
                headers={"X-Revalidation-Secret": settings.revalidation_secret},
            )
            response.raise_for_status()
            logger.info("ISR revalidation triggered for path: %s", path)
    except Exception as e:
        logger.error("Failed to trigger ISR revalidation for %s: %s", path, e)
