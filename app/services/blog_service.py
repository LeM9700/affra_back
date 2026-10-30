"""Blog business rules shared by the admin API and the content seed script."""
from app.services.revalidation_service import trigger_revalidation


async def revalidate_blog(slug: str, *, article_page: bool) -> None:
    """Revalidate the blog index and, when relevant, the article page.

    Must be called AFTER the transaction is committed: the frontend re-reads the API
    as soon as it is notified, and would otherwise cache the previous state.

    Args:
        slug: Slug of the affected article.
        article_page: Whether the article URL is (or just stopped being) public. A draft
            that stays a draft is skipped: its URL never existed, and the frontend would
            report it to search engines (IndexNow).
    """
    await trigger_revalidation("/blog")
    if article_page:
        await trigger_revalidation(f"/blog/{slug}")
