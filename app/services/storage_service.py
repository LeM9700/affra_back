"""Stockage des pièces justificatives (factures importées) — Cloudflare R2 via l'API S3.

Le reste de l'application dépend uniquement du protocole `DocumentStorage` : R2 en production,
`InMemoryStorage` dans les tests (aucun appel réseau). boto3 est synchrone : chaque appel est
exécuté dans un thread pour ne pas bloquer la boucle asyncio de FastAPI.
"""

import asyncio
from functools import lru_cache
from typing import Protocol

from app.config import settings

# Durée de validité d'un lien de consultation d'une facture (dashboard).
PRESIGNED_URL_SECONDS = 300


class StorageNotConfiguredError(RuntimeError):
    """Les variables R2_* ne sont pas renseignées."""


class DocumentStorage(Protocol):
    async def put(self, key: str, data: bytes, content_type: str) -> None: ...

    async def get(self, key: str) -> bytes: ...

    async def presigned_url(self, key: str, filename: str, expires_seconds: int = PRESIGNED_URL_SECONDS) -> str: ...


class R2Storage:
    """Bucket R2 privé. Les objets ne sont jamais publics : lecture via lien signé de courte durée."""

    def __init__(self, *, endpoint: str, access_key_id: str, secret_access_key: str, bucket: str) -> None:
        import boto3  # import tardif : inutile tant que le stockage n'est pas configuré
        from botocore.config import Config

        self._bucket = bucket
        self._client = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
            region_name="auto",
            config=Config(signature_version="s3v4", retries={"max_attempts": 3, "mode": "standard"}),
        )

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        await asyncio.to_thread(
            self._client.put_object, Bucket=self._bucket, Key=key, Body=data, ContentType=content_type
        )

    async def get(self, key: str) -> bytes:
        response = await asyncio.to_thread(self._client.get_object, Bucket=self._bucket, Key=key)
        return await asyncio.to_thread(response["Body"].read)

    async def presigned_url(self, key: str, filename: str, expires_seconds: int = PRESIGNED_URL_SECONDS) -> str:
        safe_name = "".join(ch for ch in filename if ch.isalnum() or ch in "._-") or "facture.pdf"
        return await asyncio.to_thread(
            self._client.generate_presigned_url,
            "get_object",
            Params={
                "Bucket": self._bucket,
                "Key": key,
                "ResponseContentDisposition": f'inline; filename="{safe_name}"',
            },
            ExpiresIn=expires_seconds,
        )


class InMemoryStorage:
    """Stockage en mémoire pour les tests."""

    def __init__(self) -> None:
        self.objects: dict[str, tuple[bytes, str]] = {}

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        self.objects[key] = (data, content_type)

    async def get(self, key: str) -> bytes:
        return self.objects[key][0]

    async def presigned_url(self, key: str, filename: str, expires_seconds: int = PRESIGNED_URL_SECONDS) -> str:
        return f"https://storage.test/{key}?expires={expires_seconds}"


@lru_cache(maxsize=1)
def _r2_storage() -> R2Storage:
    return R2Storage(
        endpoint=settings.r2_endpoint,
        access_key_id=settings.r2_access_key_id,
        secret_access_key=settings.r2_secret_access_key,
        bucket=settings.r2_bucket,
    )


def get_storage() -> DocumentStorage:
    """Dépendance FastAPI : le stockage configuré (remplacé par InMemoryStorage dans les tests).

    Raises:
        StorageNotConfiguredError: Si les variables R2_* sont absentes.
    """
    if not settings.r2_configured:
        raise StorageNotConfiguredError("Stockage des factures non configuré (variables R2_*)")
    return _r2_storage()
