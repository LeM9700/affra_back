from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db, verify_api_key
from app.models.blog import BlogPost
from app.schemas.blog import BlogPostListItem, BlogPostPublic

router = APIRouter(dependencies=[Depends(verify_api_key)])


@router.get("", response_model=list[BlogPostListItem])
async def list_posts(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(BlogPost)
        .where(BlogPost.published == True)  # noqa: E712
        .order_by(BlogPost.published_at.desc())
    )
    return result.scalars().all()


@router.get("/{slug}", response_model=BlogPostPublic)
async def get_post(slug: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(BlogPost).where(BlogPost.slug == slug, BlogPost.published == True)  # noqa: E712
    )
    post = result.scalar_one_or_none()
    if not post:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Article not found")
    return post
