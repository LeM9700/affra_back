from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db, verify_api_key
from app.schemas.auth import LoginRequest, TokenResponse
from app.services.auth_service import (
    ACCESS_TOKEN_EXPIRE_DAYS,
    authenticate_user,
    create_access_token,
)

router = APIRouter(dependencies=[Depends(verify_api_key)])


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db)):
    user = await authenticate_user(db, str(payload.email), payload.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email ou mot de passe incorrect",
        )
    token = create_access_token(str(user.id))
    return TokenResponse(
        access_token=token,
        expires_in=ACCESS_TOKEN_EXPIRE_DAYS * 86400,
    )
