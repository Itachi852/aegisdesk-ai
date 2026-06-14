from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import decode_access_token
from app.models.user import User

bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    """
    从请求头 Bearer Token 中解析当前登录用户。

    :param credentials: HTTP Bearer 认证信息。
    :param db: 数据库会话。
    :return: 当前登录用户模型。
    """
    # 所有需要登录的接口统一从 Bearer Token 解析当前用户。
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Please login first",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = decode_access_token(credentials.credentials)
    if not user_id:
        # Token 无效或过期时直接返回 401，前端据此跳回登录页。
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Login status has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = db.get(User, int(user_id)) if user_id.isdigit() else None
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User does not exist",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user
