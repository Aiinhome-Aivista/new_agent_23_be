from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from config import settings
from database import engine, Base

app = FastAPI(
    title="Unit-Test Case Generator Agent Backend",
    version="1.0.0",
    debug=settings.DEBUG
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

@app.on_event("startup")
async def startup_event():
    # 1. Create the database automatically if it doesn't exist
    try:
        base_engine = create_async_engine(settings.BASE_DATABASE_URL, isolation_level="AUTOCOMMIT")
        async with base_engine.connect() as conn:
            await conn.execute(text(f"CREATE DATABASE IF NOT EXISTS `{settings.MYSQL_NAME}`"))
        await base_engine.dispose()
        print(f"Database {settings.MYSQL_NAME} ensured.")
    except Exception as e:
        print(f"Could not auto-create database (it might already exist): {e}")

    # 2. Create the tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

@app.get("/health")
async def health_check():
    return {"status": "ok", "environment": settings.APP_ENV}

from routers import sessions
app.include_router(sessions.router, prefix="/api/v1")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=settings.DEBUG)
