from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db, verify_api_key
from app.models.testimonial import Testimonial
from app.schemas.testimonial import TestimonialSeoItem

router = APIRouter(dependencies=[Depends(verify_api_key)])


@router.get("", response_model=list[TestimonialSeoItem])
async def list_published_testimonials(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Testimonial)
        .where(Testimonial.status == "approved", Testimonial.consent_publication == True)  # noqa: E712
        .order_by(Testimonial.published_at.desc(), Testimonial.created_at.desc())
    )
    return result.scalars().all()
