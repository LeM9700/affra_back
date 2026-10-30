"""Versioned blog articles: file parsing, repository content and database sync."""
import re

import pytest
from sqlalchemy import select

from app.models.blog import BlogPost
from app.services.blog_content_service import (
    CONTENT_DIR,
    ArticleFormatError,
    BlogArticle,
    load_articles,
    parse_article,
    sync_articles,
)

VALID = """---
slug: prix-borne
titre: Prix d'une borne : le guide
meta_description: Tout savoir sur le prix.
---
## Section

Texte avec un lien [devis](/devis).
"""

# Frontend routes an article may link to (see affra_front/src/app/(site)).
STATIC_ROUTES = {
    "/", "/offres", "/devis", "/realisations", "/zone-intervention", "/blog", "/a-propos",
    "/services/particuliers", "/services/coproprietes", "/services/professionnels", "/services/promoteurs",
}
CITY_PAGES = {
    "montpellier", "beziers", "sete", "lunel", "ganges", "nimes", "ales", "sommieres", "uzes", "vauvert",
    "beaucaire", "le-grau-du-roi", "saint-gilles", "remoulins", "garons", "quissac", "vergeze",
}


def test_parse_valid_article():
    article = parse_article(VALID)
    assert article.slug == "prix-borne"
    assert article.titre == "Prix d'une borne : le guide"
    assert article.contenu_markdown.startswith("## Section")
    assert article.og_image_url is None


@pytest.mark.parametrize(
    "text, message",
    [
        ("## Pas de front matter\n", "front matter"),
        (VALID.replace("slug: prix-borne", "slug: Prix Borne"), "slug"),
        (VALID.replace("Tout savoir sur le prix.", "x" * 161), "meta_description"),
        (VALID.replace("meta_description: Tout savoir sur le prix.\n", ""), "meta_description is required"),
        (VALID.replace("## Section", "# Titre en double"), "H1"),
        (VALID.replace("slug: prix-borne", "slug: prix-borne\nauteur: moi"), "invalid front matter"),
    ],
)
def test_parse_rejects_invalid_articles(text, message):
    with pytest.raises(ArticleFormatError, match=message):
        parse_article(text)


def test_load_rejects_duplicate_slugs(tmp_path):
    (tmp_path / "a.md").write_text(VALID, encoding="utf-8")
    (tmp_path / "b.md").write_text(VALID, encoding="utf-8")
    with pytest.raises(ArticleFormatError, match="duplicate"):
        load_articles(tmp_path)


def test_repository_articles_are_valid_and_link_to_existing_pages():
    articles = load_articles(CONTENT_DIR)
    assert articles, "no article found in app/content/blog"
    slugs = {a.slug for a in articles}

    for article in articles:
        for path in re.findall(r"\]\((/[^)#\s]*)", article.contenu_markdown):
            path = path.rstrip("/") or "/"
            city = re.fullmatch(r"/zone-intervention/([a-z0-9-]+)", path)
            blog = re.fullmatch(r"/blog/([a-z0-9-]+)", path)
            assert (
                path in STATIC_ROUTES
                or (city and city.group(1) in CITY_PAGES)
                or (blog and blog.group(1) in slugs)
            ), f"{article.slug}: broken internal link {path}"


def _article(slug: str, titre: str = "Titre") -> BlogArticle:
    return BlogArticle(slug=slug, titre=titre, meta_description="Description.", contenu_markdown="## A\n")


async def _post(session, slug: str) -> BlogPost:
    return (await session.execute(select(BlogPost).where(BlogPost.slug == slug))).scalar_one()


async def test_sync_creates_drafts_by_default(session):
    results = await sync_articles(session, [_article("nouveau")], publish=False)
    await session.commit()

    assert [(r.action, r.published) for r in results] == [("created", False)]
    post = await _post(session, "nouveau")
    assert post.published is False and post.published_at is None


async def test_sync_publish_creates_published_articles(session):
    await sync_articles(session, [_article("nouveau")], publish=True)
    await session.commit()

    post = await _post(session, "nouveau")
    assert post.published is True and post.published_at is not None


async def test_sync_updates_existing_without_unpublishing(session):
    session.add(BlogPost(slug="existant", titre="Ancien", published=True))
    await session.commit()

    results = await sync_articles(session, [_article("existant", titre="Nouveau titre")], publish=False)
    await session.commit()

    assert [(r.action, r.published) for r in results] == [("updated", True)]
    post = await _post(session, "existant")
    assert post.titre == "Nouveau titre" and post.published is True


async def test_sync_publish_publishes_existing_draft_and_keeps_its_date(session):
    session.add(BlogPost(slug="brouillon", titre="Titre", published=False))
    await session.commit()

    results = await sync_articles(session, [_article("brouillon")], publish=True)
    await session.commit()

    assert results[0].published is True
    assert (await _post(session, "brouillon")).published_at is not None


async def test_sync_reports_unchanged_articles(session):
    await sync_articles(session, [_article("stable")], publish=True)
    await session.commit()

    results = await sync_articles(session, [_article("stable")], publish=True)

    assert results[0].action == "unchanged"
