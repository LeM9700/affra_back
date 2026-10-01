import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db, verify_api_key, verify_jwt_token
from app.models.devis import Devis
from app.schemas.devis_internal import (
    DevisEmailRequest,
    DevisInternalResponse,
    DevisListItem,
    DevisStats,
    DevisUpdate,
)
from app.services.email_service import send_custom_email

router = APIRouter(dependencies=[Depends(verify_api_key), Depends(verify_jwt_token)])

STATUSES = ["nouveau", "devis_envoye", "accepte", "installation_planifiee", "termine", "refuse", "archive"]


@router.get("", response_model=list[DevisListItem])
async def list_devis(
    db: AsyncSession = Depends(get_db),
    statut: str | None = Query(None),
    search: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    query = select(Devis).order_by(Devis.created_at.desc())

    if statut and statut in STATUSES:
        query = query.where(Devis.statut == statut)

    if search:
        # La colonne `nom` a été supprimée par la migration 0003 : ne pas la réintroduire ici.
        pattern = f"%{search}%"
        query = query.where(
            Devis.prenom.ilike(pattern)
            | Devis.email.ilike(pattern)
            | Devis.telephone.ilike(pattern)
            | Devis.ville.ilike(pattern)
        )

    query = query.limit(limit).offset(offset)
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/stats", response_model=DevisStats)
async def devis_stats(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Devis.statut, func.count()).group_by(Devis.statut)
    )
    counts = {row[0]: row[1] for row in result.all()}
    total = sum(counts.values())
    return DevisStats(
        total=total,
        nouveau=counts.get("nouveau", 0),
        devis_envoye=counts.get("devis_envoye", 0),
        accepte=counts.get("accepte", 0),
        installation_planifiee=counts.get("installation_planifiee", 0),
        termine=counts.get("termine", 0),
        refuse=counts.get("refuse", 0),
        archive=counts.get("archive", 0),
    )


@router.get("/{devis_id}", response_model=DevisInternalResponse)
async def get_devis(devis_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Devis).where(Devis.id == devis_id))
    devis = result.scalar_one_or_none()
    if not devis:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Devis not found")
    return devis


@router.patch("/{devis_id}", response_model=DevisInternalResponse)
async def update_devis(
    devis_id: uuid.UUID,
    payload: DevisUpdate,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Devis).where(Devis.id == devis_id))
    devis = result.scalar_one_or_none()
    if not devis:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Devis not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(devis, field, value)
    await db.flush()
    return devis


@router.post("/{devis_id}/email", status_code=status.HTTP_200_OK)
async def email_devis_client(
    devis_id: uuid.UUID,
    payload: DevisEmailRequest,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Devis).where(Devis.id == devis_id))
    devis = result.scalar_one_or_none()
    if not devis:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Devis not found")
    if not devis.email:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No email for this client")

    await send_custom_email(to=devis.email, subject=payload.subject, html_body=payload.message)

    # Append to notes
    note_entry = f"[Email envoyé] {payload.subject}"
    devis.notes = f"{devis.notes}\n{note_entry}" if devis.notes else note_entry
    await db.flush()

    return {"sent": True}
