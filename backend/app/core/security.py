from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings

ALGORITHM = "HS256"
pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")


def hash_password(password: str) -> str:
    """
    对用户密码进行哈希加密。

    :param password: 明文密码。
    :return: 密码哈希值。
    """
    # 只保存密码哈希，不把明文密码写入数据库。
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """
    校验明文密码是否匹配数据库中的密码哈希。

    :param password: 明文密码。
    :param password_hash: 数据库中的密码哈希。
    :return: 密码是否匹配。
    """
    return pwd_context.verify(password, password_hash)


def create_access_token(subject: str, expires_minutes: int = 60 * 24) -> str:
    """
    创建 JWT 访问令牌。

    :param subject: 令牌主体，当前项目中为用户 ID。
    :param expires_minutes: 令牌有效分钟数。
    :return: JWT 字符串。
    """
    expire = datetime.now(timezone.utc) + timedelta(minutes=expires_minutes)
    # sub 存用户 ID，后续依赖通过它恢复当前登录用户。
    payload = {"sub": subject, "exp": expire}
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=ALGORITHM)


def decode_access_token(token: str) -> str | None:
    """
    解析 JWT 访问令牌并返回主体。

    :param token: JWT 字符串。
    :return: 令牌主体，解析失败时返回 None。
    """
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[ALGORITHM])
        subject = payload.get("sub")
        return subject if isinstance(subject, str) else None
    except JWTError:
        return None
