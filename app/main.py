from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import router as v1_router
from app.api.internal.router import router as internal_router
from app.api.auth import router as auth_router
from app.config import settings
from app.jobs.cleanup import start_scheduler, stop_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(
    title="AFFRA Réseaux API",
    version="1.0.0",
    docs_url="/docs" if settings.is_dev else None,
    redoc_url=None,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["X-API-Key", "X-Revalidation-Secret", "Content-Type"],
)

app.include_router(v1_router, prefix="/api/v1")
app.include_router(internal_router, prefix="/internal")
app.include_router(auth_router, prefix="/auth", tags=["auth"])


@app.get("/health")
async def health_check():
    return {"status": "ok"}
