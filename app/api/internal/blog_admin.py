import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db, verify_api_key
from app.models.blog import BlogPost
from app.schemas.blog import BlogPostCreate, BlogPostPublic, BlogPostUpdate
from app.services.revalidation_service import trigger_revalidation

router = APIRouter(dependencies=[Depends(verify_api_key)])


@router.post("", response_model=BlogPostPublic, status_code=status.HTTP_201_CREATED)
async def create_post(payload: BlogPostCreate, db: AsyncSession = Depends(get_db)):
    post = BlogPost(**payload.model_dump())
    db.add(post)
    await db.flush()
    await trigger_revalidation("/blog")
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
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(post, field, value)
    await db.flush()
    await trigger_revalidation("/blog")
    await trigger_revalidation(f"/blog/{post.slug}")
    return post


@router.delete("/{post_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_post(post_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(BlogPost).where(BlogPost.id == post_id))
    post = result.scalar_one_or_none()
    if not post:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")
    await db.delete(post)
    await trigger_revalidation("/blog")
