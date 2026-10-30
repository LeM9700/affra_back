"""
Sync the versioned blog articles (app/content/blog/*.md) into the database.

    python -m app.scripts.seed_blog_posts             # new articles as drafts
    python -m app.scripts.seed_blog_posts --publish   # publish new articles and drafts
    python -m app.scripts.seed_blog_posts --dry-run   # validate files only

Existing articles are updated in place and keep their publication status. After the
commit, the frontend is revalidated (and reports public URLs to IndexNow) when
NEXTJS_REVALIDATE_URL is set.
"""
import argparse
import asyncio

from app.services.blog_content_service import load_articles, sync_articles


async def seed(publish: bool, dry_run: bool) -> None:
    articles = load_articles()
    if dry_run:
        for article in articles:
            print(f"OK  {article.slug}  ({len(article.contenu_markdown.split())} words)")
        return

    # Imported here so that --dry-run works without database settings.
    from app.database import AsyncSessionLocal
    from app.services.blog_service import revalidate_blog

    async with AsyncSessionLocal() as session:
        results = await sync_articles(session, articles, publish=publish)
        await session.commit()

    for result in results:
        status = "published" if result.published else "draft"
        print(f"{result.action:<9} {status:<9} {result.slug}")
        if result.action != "unchanged":
            await revalidate_blog(result.slug, article_page=result.published)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--publish", action="store_true", help="publish new articles and existing drafts")
    parser.add_argument("--dry-run", action="store_true", help="validate the files without touching the database")
    args = parser.parse_args()
    asyncio.run(seed(publish=args.publish, dry_run=args.dry_run))
