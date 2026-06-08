import uuid

import pytest_asyncio
from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import StaticPool

from suzorako.database import accounts, metadata


@pytest_asyncio.fixture
async def db() -> AsyncSession:
    """Session sur une base SQLite en mémoire, fraîche à chaque test."""
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(metadata.create_all)
    async with AsyncSession(engine) as session:
        yield session
    await engine.dispose()


async def add_account(
    db: AsyncSession,
    name: str,
    account_type: str,
    *,
    parent_id: int | None = None,
    placeholder: int = 0,
) -> int:
    result = await db.execute(
        insert(accounts)
        .values(
            guid=str(uuid.uuid4()),
            name=name,
            account_type=account_type,
            parent_id=parent_id,
            placeholder=placeholder,
        )
        .returning(accounts.c.id)
    )
    await db.commit()
    return result.scalar()
