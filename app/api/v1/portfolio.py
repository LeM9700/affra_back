from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db, verify_api_key
from app.models.portfolio import PortfolioItem
from app.schemas.portfolio import PortfolioItemPublic

router = APIRouter(dependencies=[Depends(verify_api_key)])


@router.get("", response_model=list[PortfolioItemPublic])
async def list_portfolio(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(PortfolioItem)
        .where(PortfolioItem.published == True)  # noqa: E712
        .order_by(PortfolioItem.created_at.desc())
    )
    return result.scalars().all()
