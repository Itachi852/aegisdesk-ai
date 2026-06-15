import hashlib
import logging
from pathlib import Path
from uuid import uuid4

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.knowledge import KnowledgeChunk, KnowledgeDocument
from app.services.document_service import parse_document
from app.services.vector_service import delete_document_vectors, upsert_chunks
from app.utils.text_splitter import split_text

logger = logging.getLogger(__name__)

UPLOAD_DIR = Path("uploads/knowledge")
SUPPORTED_SUFFIXES = {".txt", ".md"}


class DuplicateKnowledgeDocumentError(Exception):
    """
    表示上传内容与已存在的就绪文档重复。
    """


class KnowledgeDocumentProcessingError(Exception):
    """
    表示相同内容文档正在处理中。
    """


def calculate_content_hash(content: bytes) -> str:
    """
    计算文件内容 sha256。

    :param content: 文件二进制内容。
    :return: sha256 十六进制字符串。
    """
    return hashlib.sha256(content).hexdigest()


def import_knowledge_document(
    db: Session,
    *,
    filename: str,
    content: bytes,
    fail_on_duplicate: bool = True,
) -> tuple[KnowledgeDocument, int, bool]:
    """
    导入知识库文档，完成解析、切片、入库和向量写入。

    :param db: 数据库会话。
    :param filename: 原始文件名。
    :param content: 文件二进制内容。
    :param fail_on_duplicate: 重复就绪文档是否抛出异常；启动初始化传 False 用于幂等跳过。
    :return: 文档对象、chunk 数量、是否跳过导入。
    """
    suffix = Path(filename or "").suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        raise ValueError("仅支持 .txt 和 .md 文件")

    file_hash = calculate_content_hash(content)
    existing_document = db.scalar(select(KnowledgeDocument).where(KnowledgeDocument.file_hash == file_hash))
    if existing_document is not None and existing_document.status == "就绪":
        if fail_on_duplicate:
            raise DuplicateKnowledgeDocumentError("已存在相同内容的文档")
        chunk_count = db.scalar(
            select(func.count(KnowledgeChunk.id)).where(KnowledgeChunk.document_id == existing_document.id)
        )
        return existing_document, int(chunk_count or 0), True
    if existing_document is not None and existing_document.status == "处理中":
        raise KnowledgeDocumentProcessingError("相同文档正在处理中")

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    saved_path = UPLOAD_DIR / f"{uuid4().hex}{suffix}"
    saved_path.write_bytes(content)

    if existing_document is not None and existing_document.status == "失败":
        document = existing_document
        try:
            # 失败文档重试时先清理可能残留的 MySQL chunk 和 Qdrant 向量，再复用原记录。
            delete_document_vectors(document.id)
        except Exception:
            logger.exception("重试失败文档前清理 Qdrant 向量失败，document_id=%s", document.id)
        db.execute(delete(KnowledgeChunk).where(KnowledgeChunk.document_id == document.id))
        document.name = filename or saved_path.name
        document.file_type = suffix.lstrip(".")
        document.status = "处理中"
        document.error_message = None
        db.add(document)
        db.commit()
        db.refresh(document)
    else:
        # 先落一条处理中记录，前端可以立即看到上传任务状态。
        document = KnowledgeDocument(
            name=filename or saved_path.name,
            file_type=suffix.lstrip("."),
            file_hash=file_hash,
            status="处理中",
        )
        db.add(document)
        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            logger.info("重复知识库文档并发上传被唯一索引拦截，filename=%s", filename)
            raise DuplicateKnowledgeDocumentError("已存在相同内容的文档") from exc
        db.refresh(document)

    try:
        text = parse_document(str(saved_path))
        chunks = split_text(text)
        if not chunks:
            raise ValueError("文档内容为空")

        chunk_models = [
            KnowledgeChunk(
                document_id=document.id,
                vector_id="",
                content=chunk,
                summary=chunk[:120],
            )
            for chunk in chunks
        ]
        db.add_all(chunk_models)
        db.flush()

        # 先 flush 获取 MySQL chunk id，再复用它作为 Qdrant point id，便于后续按文档删除向量。
        for chunk in chunk_models:
            chunk.vector_id = str(chunk.id)

        # MySQL chunk 和 Qdrant 向量需要保持一致；向量写入失败时会回滚本次 chunk 入库。
        upsert_chunks(
            [
                {
                    "id": chunk.id,
                    "document_id": document.id,
                    "doc_name": document.name,
                    "content": chunk.content,
                    "summary": chunk.summary,
                }
                for chunk in chunk_models
            ]
        )

        document.status = "就绪"
        document.error_message = None
        db.add(document)
        db.commit()
        db.refresh(document)
        return document, len(chunks), False
    except Exception as exc:
        logger.exception("知识库文档处理失败，document_id=%s, filename=%s", document.id, filename)
        db.rollback()
        try:
            # 如果 Qdrant 已写入但后续步骤失败，按 document_id 清理残留向量。
            delete_document_vectors(document.id)
        except Exception:
            logger.exception("知识库文档处理失败后清理 Qdrant 向量失败，document_id=%s", document.id)
        document = db.get(KnowledgeDocument, document.id)
        # 失败只保留 document 记录和错误信息，不保留不完整的 chunk 数据。
        document.status = "失败"
        document.error_message = str(exc)
        db.add(document)
        db.commit()
        db.refresh(document)
        return document, 0, False
