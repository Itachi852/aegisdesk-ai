import logging
from pathlib import Path

from sqlalchemy import create_engine, text

import app.models  # noqa: F401  # 确保所有 ORM 模型注册到 Base.metadata。
from app.core.config import settings
from app.core.database import Base, SessionLocal, engine
from app.services.knowledge_import_service import (
    DuplicateKnowledgeDocumentError,
    KnowledgeDocumentProcessingError,
    SUPPORTED_SUFFIXES,
    import_knowledge_document,
)

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
TESTDOCS_DIR = PROJECT_ROOT / "testdocs"


def _quote_mysql_identifier(value: str) -> str:
    """
    转义 MySQL 标识符，用于 CREATE DATABASE。

    :param value: 数据库名。
    :return: 反引号包裹后的标识符。
    """
    return f"`{value.replace('`', '``')}`"


def create_mysql_database() -> None:
    """
    在 MySQL Server 上创建项目数据库。

    :return: None。
    """
    server_engine = create_engine(settings.mysql_server_url, pool_pre_ping=True)
    try:
        with server_engine.begin() as conn:
            conn.execute(
                text(
                    f"CREATE DATABASE IF NOT EXISTS {_quote_mysql_identifier(settings.mysql_db_name)} "
                    "DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
                )
            )
    finally:
        server_engine.dispose()


def create_database_tables() -> None:
    """
    根据 SQLAlchemy ORM 模型创建项目表。

    :return: None。
    """
    Base.metadata.create_all(bind=engine)


def import_test_documents() -> None:
    """
    将 testdocs 目录下的测试文档导入企业知识库。

    :return: None。
    """
    if not TESTDOCS_DIR.exists():
        logger.warning("testdocs 目录不存在，跳过测试文档导入：%s", TESTDOCS_DIR)
        return

    files = sorted(
        [path for path in TESTDOCS_DIR.iterdir() if path.is_file() and path.suffix.lower() in SUPPORTED_SUFFIXES],
        key=lambda item: item.name,
    )
    if not files:
        logger.info("testdocs 目录下没有可导入的 .txt/.md 文档。")
        return

    with SessionLocal() as db:
        for path in files:
            try:
                document, chunk_count, skipped = import_knowledge_document(
                    db,
                    filename=path.name,
                    content=path.read_bytes(),
                    fail_on_duplicate=False,
                )
                if skipped:
                    logger.info(
                        "启动初始化跳过已存在文档，document_id=%s, filename=%s, chunks=%s",
                        document.id,
                        path.name,
                        chunk_count,
                    )
                elif document.status == "失败":
                    logger.error(
                        "启动初始化导入文档失败，document_id=%s, filename=%s, error=%s",
                        document.id,
                        path.name,
                        document.error_message,
                    )
                else:
                    logger.info(
                        "启动初始化导入文档完成，document_id=%s, filename=%s, chunks=%s",
                        document.id,
                        path.name,
                        chunk_count,
                    )
            except (DuplicateKnowledgeDocumentError, KnowledgeDocumentProcessingError) as exc:
                logger.info("启动初始化跳过文档，filename=%s, reason=%s", path.name, exc)
            except Exception:
                # 单个文档失败不阻断服务启动，避免外部 Embedding/Qdrant 短暂不可用导致整体不可用。
                logger.exception("启动初始化导入文档异常，filename=%s", path.name)


def bootstrap_project() -> None:
    """
    执行项目启动初始化：创建数据库、创建表、导入测试知识库。

    :return: None。
    """
    logger.info("开始执行项目启动初始化。")
    create_mysql_database()
    create_database_tables()
    import_test_documents()
    logger.info("项目启动初始化完成。")
