from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db, verify_api_key
from app.middleware.rate_limit import check_devis_rate_limit, get_client_ip
from app.schemas.devis import DevisCreate, DevisResponse
from app.services.devis_service import create_devis

router = APIRouter(dependencies=[Depends(verify_api_key)])


@router.post("", response_model=DevisResponse, status_code=status.HTTP_201_CREATED)
async def submit_devis(
    request: Request,
    payload: DevisCreate,
    db: AsyncSession = Depends(get_db),
):
    await check_devis_rate_limit(get_client_ip(request))
    return await create_devis(db, payload)
