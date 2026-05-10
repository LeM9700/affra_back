from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db, verify_api_key
from app.models.zones import Zone
from app.schemas.zones import ZonePublic

router = APIRouter(dependencies=[Depends(verify_api_key)])


@router.get("", response_model=list[ZonePublic])
async def list_zones(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Zone)
        .where(Zone.active == True)  # noqa: E712
        .order_by(Zone.departement, Zone.ville)
    )
    return result.scalars().all()
