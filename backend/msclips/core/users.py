"""M1 runs in single-user local mode. OAuth login replaces this dependency before any multi-user deploy."""

import uuid

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from msclips.core.db import get_session
from msclips.models import User

LOCAL_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
LOCAL_USER_EMAIL = "local@msclips.invalid"


async def ensure_local_user(session: AsyncSession) -> User:
    await session.execute(
        insert(User)
        .values(id=LOCAL_USER_ID, email=LOCAL_USER_EMAIL, display_name="Local user")
        .on_conflict_do_nothing(index_elements=[User.id])
    )
    await session.commit()
    return (await session.execute(select(User).where(User.id == LOCAL_USER_ID))).scalar_one()


async def current_user(session: AsyncSession = Depends(get_session)) -> User:
    user = await session.get(User, LOCAL_USER_ID)
    if user is None:
        user = await ensure_local_user(session)
    return user
