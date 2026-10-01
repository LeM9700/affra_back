from fastapi import APIRouter

from app.api.internal import (
	billing_admin,
	blog_admin,
	devis_admin,
	leads_admin,
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
router.include_router(leads_admin.router, prefix="/leads", tags=["internal-leads"])
router.include_router(billing_admin.invoices_router, prefix="/invoices", tags=["internal-invoices"])
router.include_router(billing_admin.commissions_router, prefix="/commissions", tags=["internal-commissions"])
router.include_router(billing_admin.attribution_router, prefix="/attribution", tags=["internal-attribution"])
