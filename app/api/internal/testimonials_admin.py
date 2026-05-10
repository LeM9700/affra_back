import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db, verify_api_key, verify_jwt_token
from app.models.testimonial import Testimonial
from app.schemas.testimonial import TestimonialCreate, TestimonialPublic, TestimonialStatusUpdate

router = APIRouter(dependencies=[Depends(verify_api_key)])


@router.post("/collect", response_model=TestimonialPublic, status_code=status.HTTP_201_CREATED)
async def collect_testimonial(payload: TestimonialCreate, db: AsyncSession = Depends(get_db)):
    if payload.website:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Spam detected")

    if not payload.consent_publication:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Consentement de publication requis",
        )

    testimonial = Testimonial(**payload.model_dump(exclude={"website"}))
    db.add(testimonial)
    await db.flush()
    return testimonial


@router.get("", response_model=list[TestimonialPublic], dependencies=[Depends(verify_jwt_token)])
async def list_testimonials(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Testimonial).order_by(Testimonial.created_at.desc()))
    return result.scalars().all()


@router.patch("/{testimonial_id}/status", response_model=TestimonialPublic, dependencies=[Depends(verify_jwt_token)])
async def update_testimonial_status(
    testimonial_id: uuid.UUID,
    payload: TestimonialStatusUpdate,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Testimonial).where(Testimonial.id == testimonial_id))
    testimonial = result.scalar_one_or_none()
    if not testimonial:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Testimonial not found")

    testimonial.status = payload.status
    testimonial.published_at = datetime.now(timezone.utc) if payload.status == "approved" else None
    await db.flush()
    return testimonial
