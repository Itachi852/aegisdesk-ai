import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import admin, auth, chat, feedback, knowledge, sessions
from app.core.config import settings
from app.core.logger import setup_logging
from app.services.bootstrap_service import bootstrap_project

setup_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """
    FastAPI 启动生命周期钩子。

    :param _app: FastAPI 应用实例。
    :return: 异步上下文管理器。
    """
    if settings.bootstrap_on_startup:
        logger.info("BOOTSTRAP_ON_STARTUP=true，开始执行启动初始化。")
        bootstrap_project()
    else:
        logger.info("BOOTSTRAP_ON_STARTUP=false，跳过启动初始化。")
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix=settings.api_prefix)
app.include_router(chat.router, prefix=settings.api_prefix)
app.include_router(sessions.router, prefix=settings.api_prefix)
app.include_router(knowledge.router, prefix=settings.api_prefix)
app.include_router(feedback.router, prefix=settings.api_prefix)
app.include_router(admin.router, prefix=settings.api_prefix)


@app.get("/health")
def health_check():
    """
    后端健康检查接口。

    :return: 服务运行状态。
    """
    return {"status": "ok", "service": settings.app_name}
