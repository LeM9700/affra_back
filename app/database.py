from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings

# asyncpg tente SSL par défaut ; PostgreSQL local ne l'active généralement pas
# → WinError 10054 / ConnectionDoesNotExistError dès le premier connect
_connect_args = {"ssl": False} if settings.is_dev else {}

engine = create_async_engine(
    settings.database_url,
    echo=settings.is_dev,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
    pool_recycle=300,
    pool_timeout=30,
    connect_args=_connect_args,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)
