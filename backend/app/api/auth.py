from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.core.security import create_access_token, hash_password, verify_password
from app.models.user import User
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse, UserResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, db: Session = Depends(get_db)):
    """
    注册新用户并返回登录令牌。

    :param payload: 注册请求参数。
    :param db: 数据库会话。
    :return: 访问令牌和用户信息。
    """
    conditions = []
    if payload.email:
        conditions.append(User.email == payload.email)
    if payload.phone:
        conditions.append(User.phone == payload.phone)

    existing_user = db.scalar(select(User).where(or_(*conditions)))
    if existing_user:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="邮箱或手机号已被注册")

    user = User(
        email=payload.email,
        phone=payload.phone,
        password_hash=hash_password(payload.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_access_token(
        subject=str(user.id),
        expires_minutes=settings.access_token_expire_minutes,
    )
    return TokenResponse(access_token=token, user=UserResponse.model_validate(user))


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    """
    校验账号密码并返回登录令牌。

    :param payload: 登录请求参数。
    :param db: 数据库会话。
    :return: 访问令牌和用户信息。
    """
    account = payload.account.strip().lower()
    user = db.scalar(select(User).where(or_(User.email == account, User.phone == account)))

    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="账号或密码错误，请重新输入")

    token = create_access_token(
        subject=str(user.id),
        expires_minutes=settings.access_token_expire_minutes,
    )
    return TokenResponse(access_token=token, user=UserResponse.model_validate(user))


@router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)):
    """
    获取当前登录用户信息。

    :param current_user: 当前登录用户。
    :return: 当前用户信息。
    """
    return current_user
