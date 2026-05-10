from fastapi import APIRouter

from app.api.v1 import blog, devis, portfolio, testimonials, zones

router = APIRouter()
router.include_router(devis.router, prefix="/devis", tags=["devis"])
router.include_router(blog.router, prefix="/blog", tags=["blog"])
router.include_router(portfolio.router, prefix="/portfolio", tags=["portfolio"])
router.include_router(testimonials.router, prefix="/testimonials", tags=["testimonials"])
router.include_router(zones.router, prefix="/zones", tags=["zones"])
