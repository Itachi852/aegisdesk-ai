from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from app.core.config import settings

# pool_pre_ping 会在复用连接前探活，减少 MySQL 空闲连接断开导致的请求失败。
engine = create_engine(settings.mysql_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


class Base(DeclarativeBase):
    """
    SQLAlchemy ORM 模型基类。
    """
    pass


def get_db():
    """
    获取 FastAPI 请求生命周期内使用的数据库会话。

    :return: 数据库会话生成器。
    """
    db = SessionLocal()
    try:
        # FastAPI 依赖会把同一个请求内的 db 注入到接口，响应结束后统一关闭。
        yield db
    finally:
        db.close()
