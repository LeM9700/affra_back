from fastapi import APIRouter

from app.api.internal import (
	blog_admin,
	devis_admin,
	portfolio_admin,
	revalidate,
	testimonials_admin,
	zones_admin,
)

router = APIRouter()
router.include_router(devis_admin.router, prefix="/devis", tags=["internal-devis"])
router.include_router(blog_admin.router, prefix="/blog", tags=["internal-blog"])
router.include_router(portfolio_admin.router, prefix="/portfolio", tags=["internal-portfolio"])
router.include_router(testimonials_admin.router, prefix="/testimonials", tags=["internal-testimonials"])
router.include_router(zones_admin.router, prefix="/zones", tags=["internal-zones"])
router.include_router(revalidate.router, prefix="/revalidate", tags=["internal-revalidate"])
