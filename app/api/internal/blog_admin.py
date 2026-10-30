import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db, verify_api_key
from app.models.blog import BlogPost
from app.schemas.blog import BlogPostCreate, BlogPostPublic, BlogPostUpdate
from app.services.blog_service import revalidate_blog

router = APIRouter(dependencies=[Depends(verify_api_key)])


@router.post("", response_model=BlogPostPublic, status_code=status.HTTP_201_CREATED)
async def create_post(payload: BlogPostCreate, db: AsyncSession = Depends(get_db)):
    post = BlogPost(**payload.model_dump())
    db.add(post)
    await db.commit()
    await revalidate_blog(post.slug, article_page=post.published)
    return post


@router.put("/{post_id}", response_model=BlogPostPublic)
async def update_post(
    post_id: uuid.UUID,
    payload: BlogPostUpdate,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(BlogPost).where(BlogPost.id == post_id))
    post = result.scalar_one_or_none()
    if not post:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")
    was_published = post.published
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(post, field, value)
    await db.commit()
    # Unpublishing also revalidates the article page, so that it turns into a 404.
    await revalidate_blog(post.slug, article_page=was_published or post.published)
    return post


@router.delete("/{post_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_post(post_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(BlogPost).where(BlogPost.id == post_id))
    post = result.scalar_one_or_none()
    if not post:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")
    slug, was_published = post.slug, post.published
    await db.delete(post)
    await db.commit()
    # Without revalidating the article page, a deleted article stays cached and online.
    await revalidate_blog(slug, article_page=was_published)
