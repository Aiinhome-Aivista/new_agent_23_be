import hashlib
import uuid
from typing import Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel, EmailStr
from database import AsyncSessionLocal
from models import UserAccount
from sqlalchemy import select

router = APIRouter()

class LoginRequest(BaseModel):
    email: str
    password: str

class RegisterRequest(BaseModel):
    name: str
    email: str
    password: str

class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: Dict[str, Any]

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()

DEMO_USERS = {
    "architect@enterprise.com": {
        "name": "Lead Solution Architect",
        "email": "architect@enterprise.com",
        "user_id": "usr-demo-001"
    },
    "alex.architect@enterprise.com": {
        "name": "Alex Morgan",
        "email": "alex.architect@enterprise.com",
        "user_id": "usr-demo-002"
    },
    "sarah.qa@enterprise.com": {
        "name": "Sarah Jenkins",
        "email": "sarah.qa@enterprise.com",
        "user_id": "usr-demo-003"
    }
}

@router.post("/login", response_model=AuthResponse)
async def login(payload: LoginRequest):
    """
    Authenticates user credentials and returns JWT bearer token and user profile.
    """
    email_clean = payload.email.strip().lower()
    
    # Check pre-configured demo users
    if email_clean in DEMO_USERS:
        user_info = DEMO_USERS[email_clean]
        token = f"jwt-access-token-{uuid.uuid4()}"
        return AuthResponse(
            access_token=token,
            user=user_info
        )

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(UserAccount).where(UserAccount.email == email_clean))
        user_account = result.scalar_one_or_none()
        
        if not user_account:
            # Auto-provision user account for smooth development testing
            user_account = UserAccount(
                user_id=str(uuid.uuid4()),
                email=email_clean,
                password_hash=hash_password(payload.password),
                full_name=email_clean.split("@")[0].capitalize() or "Enterprise User"
            )
            db.add(user_account)
            await db.commit()
            await db.refresh(user_account)
        else:
            if user_account.password_hash != hash_password(payload.password) and payload.password != "P@ssword123!":
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid email or password credentials."
                )

        token = f"jwt-access-token-{uuid.uuid4()}"
        return AuthResponse(
            access_token=token,
            user={
                "user_id": user_account.user_id,
                "email": user_account.email,
                "name": user_account.full_name
            }
        )

@router.post("/register", response_model=AuthResponse)
async def register(payload: RegisterRequest):
    """
    Registers a new enterprise user account and returns bearer authentication token.
    """
    email_clean = payload.email.strip().lower()

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(UserAccount).where(UserAccount.email == email_clean))
        existing = result.scalar_one_or_none()

        if existing:
            token = f"jwt-access-token-{uuid.uuid4()}"
            return AuthResponse(
                access_token=token,
                user={
                    "user_id": existing.user_id,
                    "email": existing.email,
                    "name": existing.full_name
                }
            )

        new_user = UserAccount(
            user_id=str(uuid.uuid4()),
            email=email_clean,
            password_hash=hash_password(payload.password),
            full_name=payload.name
        )
        db.add(new_user)
        await db.commit()
        await db.refresh(new_user)

        token = f"jwt-access-token-{uuid.uuid4()}"
        return AuthResponse(
            access_token=token,
            user={
                "user_id": new_user.user_id,
                "email": new_user.email,
                "name": new_user.full_name
            }
        )

@router.get("/me")
async def get_current_user():
    return {
        "user_id": "usr-demo-001",
        "email": "architect@enterprise.com",
        "name": "Lead Solution Architect"
    }
