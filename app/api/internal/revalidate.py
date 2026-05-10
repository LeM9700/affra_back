from fastapi import APIRouter, Depends, status

from app.dependencies import verify_revalidation_secret
from app.services.revalidation_service import trigger_revalidation

router = APIRouter(dependencies=[Depends(verify_revalidation_secret)])


@router.post("", status_code=status.HTTP_200_OK)
async def revalidate(path: str):
    """
    Déclenche la revalidation ISR Next.js pour un chemin donné.
    Appelé par les endpoints internes après chaque mutation de contenu.
    """
    await trigger_revalidation(path)
    return {"revalidated": True, "path": path}
