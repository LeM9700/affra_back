from collections.abc import AsyncGenerator

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import APIKeyHeader
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import AsyncSessionLocal

# --- Database session dependency ---

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# --- API Key security scheme ---

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
revalidation_key_header = APIKeyHeader(name="X-Revalidation-Secret", auto_error=False)


async def verify_api_key(key: str | None = Security(api_key_header)) -> None:
    if not key or key != settings.api_secret_key:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or missing API key",
        )


async def verify_revalidation_secret(key: str | None = Security(revalidation_key_header)) -> None:
    if not key or key != settings.revalidation_secret:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or missing revalidation secret",
        )


# --- JWT Bearer token scheme ---

from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

bearer_scheme = HTTPBearer(auto_error=False)


async def verify_jwt_token(
    credentials: HTTPAuthorizationCredentials | None = Security(bearer_scheme),
) -> str:
    """Returns the user_id from the JWT token or raises 401."""
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    from app.services.auth_service import decode_access_token

    user_id = decode_access_token(credentials.credentials)
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user_id
