import logging
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.admin_user import AdminUser

logger = logging.getLogger(__name__)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_DAYS = 7


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def create_access_token(user_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS)
    payload = {"sub": user_id, "exp": expire}
    return jwt.encode(payload, settings.api_secret_key, algorithm=ALGORITHM)


def decode_access_token(token: str) -> str | None:
    """Returns user_id or None if token is invalid/expired."""
    try:
        payload = jwt.decode(token, settings.api_secret_key, algorithms=[ALGORITHM])
        return payload.get("sub")
    except JWTError:
        logger.debug("JWT decode failed")
        return None


async def authenticate_user(db: AsyncSession, email: str, password: str) -> AdminUser | None:
    result = await db.execute(select(AdminUser).where(AdminUser.email == email))
    user = result.scalar_one_or_none()
    if not user or not verify_password(password, user.hashed_pw):
        return None
    return user
