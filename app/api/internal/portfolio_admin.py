import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db, verify_api_key
from app.models.portfolio import PortfolioItem
from app.schemas.portfolio import PortfolioItemCreate, PortfolioItemPublic, PortfolioItemUpdate
from app.services.revalidation_service import trigger_revalidation

router = APIRouter(dependencies=[Depends(verify_api_key)])


@router.post("", response_model=PortfolioItemPublic, status_code=status.HTTP_201_CREATED)
async def create_item(payload: PortfolioItemCreate, db: AsyncSession = Depends(get_db)):
    item = PortfolioItem(**payload.model_dump())
    db.add(item)
    await db.flush()
    await trigger_revalidation("/realisations")
    return item


@router.put("/{item_id}", response_model=PortfolioItemPublic)
async def update_item(
    item_id: uuid.UUID,
    payload: PortfolioItemUpdate,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(PortfolioItem).where(PortfolioItem.id == item_id))
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(item, field, value)
    await db.flush()
    await trigger_revalidation("/realisations")
    return item


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_item(item_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(PortfolioItem).where(PortfolioItem.id == item_id))
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")
    await db.delete(item)
    await trigger_revalidation("/realisations")
