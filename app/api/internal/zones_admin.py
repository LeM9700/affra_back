import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db, verify_api_key
from app.models.zones import Zone
from app.schemas.zones import ZoneCreate, ZonePublic, ZoneUpdate
from app.services.revalidation_service import trigger_revalidation

router = APIRouter(dependencies=[Depends(verify_api_key)])


@router.post("", response_model=ZonePublic, status_code=status.HTTP_201_CREATED)
async def create_zone(payload: ZoneCreate, db: AsyncSession = Depends(get_db)):
    zone = Zone(**payload.model_dump())
    db.add(zone)
    await db.flush()
    await trigger_revalidation("/zone-intervention")
    return zone


@router.put("/{zone_id}", response_model=ZonePublic)
async def update_zone(
    zone_id: uuid.UUID,
    payload: ZoneUpdate,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Zone).where(Zone.id == zone_id))
    zone = result.scalar_one_or_none()
    if not zone:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Zone not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(zone, field, value)
    await db.flush()
    await trigger_revalidation("/zone-intervention")
    return zone


@router.delete("/{zone_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_zone(zone_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Zone).where(Zone.id == zone_id))
    zone = result.scalar_one_or_none()
    if not zone:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Zone not found")
    await db.delete(zone)
    await trigger_revalidation("/zone-intervention")
