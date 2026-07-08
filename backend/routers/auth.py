"""认证路由 — 注册 / 登录 / 获取当前用户"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from sqlmodel import Session, select
from database import get_session
from models import User
from auth import hash_password, verify_password, create_token, get_current_user

router = APIRouter(prefix="/api/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    nickname: str | None = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    id: str
    email: str
    nickname: str | None


class AuthResponse(BaseModel):
    token: str
    user: UserResponse


@router.post("/register", response_model=AuthResponse)
def register(req: RegisterRequest, session: Session = Depends(get_session)):
    existing = session.exec(select(User).where(User.email == req.email)).first()
    if existing:
        raise HTTPException(status_code=400, detail="该邮箱已注册")

    user = User(
        email=req.email,
        password_hash=hash_password(req.password),
        nickname=req.nickname,
    )
    session.add(user)
    session.commit()
    session.refresh(user)

    token = create_token(user.id)
    return AuthResponse(
        token=token,
        user=UserResponse(id=user.id, email=user.email, nickname=user.nickname),
    )


@router.post("/login", response_model=AuthResponse)
def login(req: LoginRequest, session: Session = Depends(get_session)):
    user = session.exec(select(User).where(User.email == req.email)).first()
    if not user or not verify_password(req.password, user.password_hash):
        raise HTTPException(status_code=401, detail="邮箱或密码错误")

    user.last_active_at = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
    session.add(user)
    session.commit()

    token = create_token(user.id)
    return AuthResponse(
        token=token,
        user=UserResponse(id=user.id, email=user.email, nickname=user.nickname),
    )


@router.get("/me", response_model=UserResponse)
def me(user: User = Depends(get_current_user)):
    return UserResponse(id=user.id, email=user.email, nickname=user.nickname)
