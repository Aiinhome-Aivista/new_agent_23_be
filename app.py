from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from database.config import settings
from database.database import engine, Base
from routers import sessions, auth, jira
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
        
        # Run local migrations for SQLite database to add new columns if they do not exist
        from sqlalchemy import text
        with engine.connect() as conn:
            # Check and add columns to requirement_decompositions
            try:
                result = conn.execute(text("PRAGMA table_info(requirement_decompositions)")).fetchall()
                existing_cols = [r[1] for r in result]
                if "story_name" not in existing_cols:
                    conn.execute(text("ALTER TABLE requirement_decompositions ADD COLUMN story_name VARCHAR(255)"))
                    print("Migration: Added story_name to requirement_decompositions")
                if "story" not in existing_cols:
                    conn.execute(text("ALTER TABLE requirement_decompositions ADD COLUMN story TEXT"))
                    print("Migration: Added story to requirement_decompositions")
            except Exception as e:
                print(f"Migration warning (requirement_decompositions): {e}")

            # Check and add columns to coverage_matrices
            try:
                result = conn.execute(text("PRAGMA table_info(coverage_matrices)")).fetchall()
                existing_cols = [r[1] for r in result]
                if "story_name" not in existing_cols:
                    conn.execute(text("ALTER TABLE coverage_matrices ADD COLUMN story_name VARCHAR(255)"))
                    print("Migration: Added story_name to coverage_matrices")
                if "story" not in existing_cols:
                    conn.execute(text("ALTER TABLE coverage_matrices ADD COLUMN story TEXT"))
                    print("Migration: Added story to coverage_matrices")
            except Exception as e:
                print(f"Migration warning (coverage_matrices): {e}")
                
    except Exception as e:
        print(f"Database startup warning: {e}")

@app.get("/health")
async def health_check():
    return {"status": "ok", "environment": "development"}

app.include_router(sessions.router, prefix="/api/v1")
app.include_router(auth.router, prefix="/api/v1/auth", tags=["Authentication"])
app.include_router(jira.router, prefix="/api/v1/jira", tags=["Jira"])

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
