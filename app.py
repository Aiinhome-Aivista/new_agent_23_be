from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from database.config import settings
from database.database import engine, Base
from routers import sessions, auth

app = FastAPI(
    title="Unit-Test Case Generator Agent Backend",
    version="1.0.0",
    debug=True
)

# CORS configuration - Allow all local dev origins dynamically to fix CORS errors
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=".*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def startup_event():
    try:
        # Create all database tables locally on startup
        Base.metadata.create_all(bind=engine)
        print("Database schema initialized successfully (utgc_agent.db).")
    except Exception as e:
        print(f"Database startup warning: {e}")

@app.get("/health")
async def health_check():
    return {"status": "ok", "environment": "development"}

app.include_router(sessions.router, prefix="/api/v1")
app.include_router(auth.router, prefix="/api/v1/auth", tags=["Authentication"])

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
