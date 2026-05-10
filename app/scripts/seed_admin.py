"""
Seed script — create the initial admin user.
Run once: python -m app.scripts.seed_admin
"""
import asyncio
import sys

from app.database import AsyncSessionLocal
from app.models.admin_user import AdminUser
from app.services.auth_service import hash_password


async def seed() -> None:
    email = "admin@affra-reseaux.fr"
    password = "admin123"  # Change immediately after first login

    async with AsyncSessionLocal() as session:
        from sqlalchemy import select
        existing = await session.execute(select(AdminUser).where(AdminUser.email == email))
        if existing.scalar_one_or_none():
            print(f"Admin user {email} already exists — skipping.")
            return

        user = AdminUser(email=email, hashed_pw=hash_password(password))
        session.add(user)
        await session.commit()
        print(f"Admin user created: {email} / {password}")
        print("⚠️  Change the password after first login!")


if __name__ == "__main__":
    asyncio.run(seed())
