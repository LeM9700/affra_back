import logging
from collections import defaultdict
from datetime import datetime, timezone

from fastapi import HTTPException, status

logger = logging.getLogger(__name__)

# In-memory store: {ip: [timestamp, ...]}
_submissions: dict[str, list[datetime]] = defaultdict(list)
RATE_LIMIT = 5
WINDOW_SECONDS = 3600  # 1 heure


async def check_devis_rate_limit(ip: str) -> None:
    now = datetime.now(timezone.utc)
    window_cutoff = now.timestamp() - WINDOW_SECONDS

    # Purge old entries
    _submissions[ip] = [t for t in _submissions[ip] if t.timestamp() > window_cutoff]

    if len(_submissions[ip]) >= RATE_LIMIT:
        logger.warning("Rate limit exceeded for IP: %s", ip)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Trop de demandes. Réessayez dans une heure.",
            headers={"Retry-After": "3600"},
        )

    _submissions[ip].append(now)
