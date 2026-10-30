"""Blog admin: frontend revalidation (ISR + IndexNow) after each mutation.

Each recorded call also captures what a separate database session sees at that moment:
the frontend re-reads the API as soon as it is notified, so the change must already be
committed.
"""
import pytest
from sqlalchemy import select

from app import database
from app.models.blog import BlogPost
from app.services import blog_service


@pytest.fixture
def revalidations(monkeypatch) -> list[tuple[str, dict[str, bool]]]:
    """Record (path, committed state of every post seen from another session) per call."""
    calls: list[tuple[str, dict[str, bool]]] = []

    async def record(path: str) -> None:
        async with database.AsyncSessionLocal() as other:
            rows = (await other.execute(select(BlogPost.slug, BlogPost.published))).all()
        calls.append((path, {slug: published for slug, published in rows}))

    monkeypatch.setattr(blog_service, "trigger_revalidation", record)
    return calls


def _paths(calls: list[tuple[str, dict[str, bool]]]) -> list[str]:
    return [path for path, _ in calls]


async def _create(client, slug: str, published: bool) -> dict:
    res = await client.post(
        "/internal/blog", json={"slug": slug, "titre": f"Article {slug}", "published": published}
    )
    assert res.status_code == 201, res.text
    return res.json()


async def test_create_published_revalidates_article_after_commit(client, revalidations):
    await _create(client, "prix-borne-2026", published=True)

    assert _paths(revalidations) == ["/blog", "/blog/prix-borne-2026"]
    for _, committed in revalidations:
        assert committed == {"prix-borne-2026": True}


async def test_create_draft_does_not_expose_article_url(client, revalidations):
    await _create(client, "brouillon", published=False)

    assert _paths(revalidations) == ["/blog"]
    assert revalidations[0][1] == {"brouillon": False}


async def test_publishing_a_draft_revalidates_article_after_commit(client, revalidations):
    post = await _create(client, "aides-advenir", published=False)
    revalidations.clear()

    res = await client.put(f"/internal/blog/{post['id']}", json={"published": True})

    assert res.status_code == 200, res.text
    assert _paths(revalidations) == ["/blog", "/blog/aides-advenir"]
    assert all(committed == {"aides-advenir": True} for _, committed in revalidations)


async def test_unpublishing_revalidates_article_so_it_becomes_404(client, revalidations):
    post = await _create(client, "ancien-article", published=True)
    revalidations.clear()

    await client.put(f"/internal/blog/{post['id']}", json={"published": False})

    assert _paths(revalidations) == ["/blog", "/blog/ancien-article"]
    assert revalidations[-1][1] == {"ancien-article": False}


async def test_editing_a_draft_keeps_its_url_private(client, revalidations):
    post = await _create(client, "brouillon", published=False)
    revalidations.clear()

    await client.put(f"/internal/blog/{post['id']}", json={"titre": "Nouveau titre"})

    assert _paths(revalidations) == ["/blog"]


async def test_delete_published_revalidates_article_after_commit(client, revalidations):
    post = await _create(client, "a-supprimer", published=True)
    revalidations.clear()

    res = await client.delete(f"/internal/blog/{post['id']}")

    assert res.status_code == 204
    assert _paths(revalidations) == ["/blog", "/blog/a-supprimer"]
    assert all(committed == {} for _, committed in revalidations)


async def test_delete_draft_only_revalidates_index(client, revalidations):
    post = await _create(client, "brouillon", published=False)
    revalidations.clear()

    await client.delete(f"/internal/blog/{post['id']}")

    assert _paths(revalidations) == ["/blog"]


async def test_unknown_post_does_not_revalidate(client, revalidations):
    res = await client.delete("/internal/blog/00000000-0000-0000-0000-000000000000")

    assert res.status_code == 404
    assert revalidations == []
