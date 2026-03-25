"""Startup database seeding utilities."""

from __future__ import annotations

from sqlalchemy import select

from app.core.config import get_settings
from app.core.security import hash_password
from app.database.models import User, UserRole
from app.database.session import get_session_factory


async def seed_admin_user() -> None:
    """Seed an admin user if credentials are available.

    - In docker/prod, provide ADMIN_* env vars.
    - In local, a default admin is seeded unless disabled.
    """
    settings = get_settings()

    username = settings.seed_admin_username
    email = settings.seed_admin_email
    password = settings.seed_admin_password

    if username is None and email is None and password is None:
        if not (settings.env == "local" and settings.seed_admin_defaults_in_local):
            return
        username = "admin"
        email = "admin@example.com"
        password = "admin123456"

    if username is None or email is None or password is None:
        # Partial configuration - don't guess.
        return

    factory = get_session_factory()
    async with factory() as session:
        existing_q = await session.execute(select(User).where(User.username == username))
        existing = existing_q.scalar_one_or_none()
        if existing is not None:
            return

        user = User(
            username=username,
            email=email,
            hashed_password=hash_password(password),
            role=UserRole.admin,
            is_active=True,
        )
        session.add(user)
        await session.commit()

