import os
import asyncio
from sqlalchemy import create_engine, select, event
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.pool import NullPool
from config import settings

# Built-in SQLite engine (Zero external dependencies, instant 0ms local connection, 100% offline & crash-proof)
DB_FILE = os.path.join(os.path.dirname(__file__), "utgc_agent.db")
SQLITE_URL = f"sqlite:///{DB_FILE}"

engine = create_engine(
    SQLITE_URL,
    connect_args={
        "check_same_thread": False,
        "timeout": 30  # Wait up to 30s for lock release
    },
    poolclass=NullPool,  # Disable connection pooling to close handles immediately
    echo=False
)

# Enable WAL (Write-Ahead Logging) and Normal sync for maximum SQLite concurrency and reliability
@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
    except Exception:
        pass
    finally:
        cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class AsyncSessionWrapper:
    """
    Async wrapper for standard SQLite sync sessions to ensure seamless compatibility 
    with async FastAPI routers and LangGraph nodes without requiring external async driver packages.
    """
    def __init__(self, sync_session):
        self._sync_session = sync_session

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            self._sync_session.rollback()
        else:
            try:
                self._sync_session.commit()
            except Exception:
                self._sync_session.rollback()
                raise
        self._sync_session.close()

    def add(self, instance):
        self._sync_session.add(instance)

    async def commit(self):
        await asyncio.to_thread(self._sync_session.commit)

    async def rollback(self):
        await asyncio.to_thread(self._sync_session.rollback)

    async def flush(self):
        await asyncio.to_thread(self._sync_session.flush)

    async def delete(self, instance):
        self._sync_session.delete(instance)

    async def execute(self, statement, params=None):
        return await asyncio.to_thread(self._sync_session.execute, statement, params)

    def scalar_one_or_none(self):
        return self._sync_session.scalar_one_or_none()

async def get_db():
    sync_session = SessionLocal()
    wrapper = AsyncSessionWrapper(sync_session)
    try:
        yield wrapper
    finally:
        sync_session.close()

def AsyncSessionLocal():
    return AsyncSessionWrapper(SessionLocal())
