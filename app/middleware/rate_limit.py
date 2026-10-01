import ipaddress
import logging
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request, status

logger = logging.getLogger(__name__)

# Header posé par le serveur Next.js (seul détenteur de X-API-Key) avec l'IP du navigateur.
# Sans lui, toutes les requêtes server-to-server partagent l'IP de la plateforme d'hébergement
# et la limite devient globale pour tous les visiteurs.
CLIENT_IP_HEADER = "X-Client-IP"


def get_client_ip(request: Request) -> str:
    """IP du visiteur. À n'appeler que sur des routes protégées par verify_api_key :
    le header n'est fiable que parce que seul le serveur Next.js connaît la clé."""
    forwarded = (request.headers.get(CLIENT_IP_HEADER) or "").strip()
    if forwarded:
        try:
            return str(ipaddress.ip_address(forwarded))
        except ValueError:
            pass
    return request.client.host if request.client else "unknown"


class SlidingWindowRateLimiter:
    """Limiteur en mémoire par clé (IP). Mono-instance : suffisant pour un seul worker Railway."""

    MAX_KEYS = 50_000  # borne mémoire face à un balayage d'IP

    def __init__(self, limit: int, window_seconds: int, detail: str) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self.detail = detail
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str) -> None:
        now = time.monotonic()
        cutoff = now - self.window_seconds
        hits = self._hits[key]
        while hits and hits[0] <= cutoff:
            hits.popleft()

        if len(hits) >= self.limit:
            logger.warning("Rate limit exceeded (%s) for key: %s", self.detail, key)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=self.detail,
                headers={"Retry-After": str(self.window_seconds)},
            )

        hits.append(now)
        if len(self._hits) > self.MAX_KEYS:
            self._purge(cutoff)

    def _purge(self, cutoff: float) -> None:
        for key in [k for k, v in self._hits.items() if not v or v[-1] <= cutoff]:
            del self._hits[key]

    def reset(self) -> None:
        self._hits.clear()


devis_limiter = SlidingWindowRateLimiter(5, 3600, "Trop de demandes. Réessayez dans une heure.")
attribution_limiter = SlidingWindowRateLimiter(60, 60, "Too many attribution events")


async def check_devis_rate_limit(ip: str) -> None:
    devis_limiter.check(ip)


async def check_attribution_rate_limit(ip: str) -> None:
    attribution_limiter.check(ip)
