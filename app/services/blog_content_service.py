"""Versioned blog articles: Markdown files in app/content/blog, synced into the database.

File format (front matter, then the Markdown body):

    ---
    slug: prix-borne-recharge
    titre: Prix d'une borne de recharge en 2026
    meta_description: Short description, 160 characters max.
    og_image_url: https://...        (optional)
    ---
    ## First section
    ...

The page title (H1) is rendered by the frontend from `titre`, so the body starts at H2.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.blog import BlogPost
from app.schemas.blog import BlogPostCreate

CONTENT_DIR = Path(__file__).resolve().parent.parent / "content" / "blog"

_FRONT_MATTER_KEYS = {"slug", "titre", "meta_description", "og_image_url"}


class ArticleFormatError(ValueError):
    """Raised when an article file is malformed or fails validation."""


@dataclass(frozen=True)
class BlogArticle:
    slug: str
    titre: str
    meta_description: str
    contenu_markdown: str
    og_image_url: str | None = None


@dataclass(frozen=True)
class SyncResult:
    slug: str
    action: Literal["created", "updated", "unchanged"]
    published: bool


def parse_article(text: str, source: str = "<string>") -> BlogArticle:
    """Parse an article file (front matter + Markdown body).

    Args:
        text: Raw file content.
        source: Name used in error messages.

    Returns:
        The validated article.

    Raises:
        ArticleFormatError: Missing front matter, unknown key, H1 in the body, or a field
            rejected by the API schema (slug pattern, meta description length...).
    """
    lines = text.lstrip("﻿").splitlines()
    if not lines or lines[0].strip() != "---" or "---" not in (line.strip() for line in lines[1:]):
        raise ArticleFormatError(f"{source}: front matter delimited by '---' is required")

    end = next(i for i, line in enumerate(lines[1:], start=1) if line.strip() == "---")
    meta: dict[str, str] = {}
    for line in lines[1:end]:
        if not line.strip():
            continue
        key, sep, value = line.partition(":")
        key = key.strip()
        if not sep or key not in _FRONT_MATTER_KEYS:
            raise ArticleFormatError(f"{source}: invalid front matter line {line!r}")
        meta[key] = value.strip()

    body = "\n".join(lines[end + 1 :]).strip() + "\n"
    if any(line.startswith("# ") for line in body.splitlines()):
        raise ArticleFormatError(f"{source}: the body must not contain an H1 (the page title is the H1)")

    try:
        validated = BlogPostCreate(
            slug=meta.get("slug", ""),
            titre=meta.get("titre", ""),
            meta_description=meta.get("meta_description") or None,
            og_image_url=meta.get("og_image_url") or None,
            contenu_markdown=body,
        )
    except ValidationError as exc:
        raise ArticleFormatError(f"{source}: {exc}") from exc
    if not validated.meta_description:
        raise ArticleFormatError(f"{source}: meta_description is required")

    return BlogArticle(
        slug=validated.slug,
        titre=validated.titre,
        meta_description=validated.meta_description,
        contenu_markdown=body,
        og_image_url=validated.og_image_url,
    )


def load_articles(directory: Path = CONTENT_DIR) -> list[BlogArticle]:
    """Load every `*.md` article of a directory, sorted by file name.

    Raises:
        ArticleFormatError: If a file is invalid or two files share a slug.
    """
    articles = [parse_article(path.read_text(encoding="utf-8"), path.name) for path in sorted(directory.glob("*.md"))]
    slugs = [a.slug for a in articles]
    duplicates = {s for s in slugs if slugs.count(s) > 1}
    if duplicates:
        raise ArticleFormatError(f"duplicate slugs: {sorted(duplicates)}")
    return articles


async def sync_articles(session: AsyncSession, articles: list[BlogArticle], *, publish: bool) -> list[SyncResult]:
    """Create or update articles by slug. Does not commit.

    Rules: a new article is a draft unless `publish` is set; an existing article keeps its
    publication status (this never unpublishes), and `publish` only publishes drafts.

    Args:
        session: Database session (the caller commits, then revalidates the frontend).
        articles: Articles to sync.
        publish: Publish new articles and existing drafts.

    Returns:
        One result per article, in the same order.
    """
    now = datetime.now(timezone.utc)
    results: list[SyncResult] = []
    for article in articles:
        post = (await session.execute(select(BlogPost).where(BlogPost.slug == article.slug))).scalar_one_or_none()
        fields = {
            "titre": article.titre,
            "meta_description": article.meta_description,
            "contenu_markdown": article.contenu_markdown,
            "og_image_url": article.og_image_url,
        }

        if post is None:
            post = BlogPost(slug=article.slug, published=publish, published_at=now if publish else None, **fields)
            session.add(post)
            results.append(SyncResult(article.slug, "created", publish))
            continue

        changed = any(getattr(post, name) != value for name, value in fields.items())
        for name, value in fields.items():
            setattr(post, name, value)
        if publish and not post.published:
            post.published = True
            post.published_at = post.published_at or now
            changed = True
        results.append(SyncResult(article.slug, "updated" if changed else "unchanged", post.published))

    await session.flush()
    return results
