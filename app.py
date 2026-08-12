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

@app.on_event("startup")
async def startup_event():
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        print("Database schema initialized successfully.")
    except Exception as e:
        print(f"Database startup warning: {e}")

@app.get("/health")
async def health_check():
    return {"status": "ok", "environment": settings.APP_ENV}

from routers import sessions
app.include_router(sessions.router, prefix="/api/v1")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=settings.DEBUG)
