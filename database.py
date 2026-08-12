import os
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import declarative_base
from config import settings

# Check if aiosqlite package is installed in current Python environment
has_aiosqlite = False
try:
    import aiosqlite
    has_aiosqlite = True
except ImportError:
    has_aiosqlite = False

# If aiosqlite is available and USE_SQLITE_FALLBACK is set, use SQLite async engine
# Otherwise use MySQL asyncmy engine (settings.DATABASE_URL)
if getattr(settings, "USE_SQLITE_FALLBACK", False) and has_aiosqlite:
    db_url = settings.SQLITE_DATABASE_URL
else:
    db_url = settings.DATABASE_URL

engine = create_async_engine(
    db_url,
    echo=False,
    future=True
)

AsyncSessionLocal = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

Base = declarative_base()

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
