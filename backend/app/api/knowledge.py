import logging
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.knowledge import KnowledgeChunk, KnowledgeDocument
from app.models.user import User
from app.schemas.knowledge import (
    KnowledgeChunkResponse,
    KnowledgeDocumentDetail,
    KnowledgeDocumentListResponse,
    KnowledgeDocumentResponse,
)
from app.services.document_service import parse_document
from app.services.vector_service import delete_document_vectors, upsert_chunks
from app.utils.text_splitter import split_text

router = APIRouter(prefix="/knowledge", tags=["knowledge"])
logger = logging.getLogger(__name__)

UPLOAD_DIR = Path("uploads/knowledge")
SUPPORTED_SUFFIXES = {".txt", ".md"}


def _document_response(document: KnowledgeDocument, chunk_count: int = 0) -> KnowledgeDocumentResponse:
    """
    将知识库文档模型转换为接口响应对象。

    :param document: 知识库文档模型。
    :param chunk_count: 文档切片数量。
    :return: 知识库文档响应对象。
    """
    return KnowledgeDocumentResponse(
        id=document.id,
        name=document.name,
        file_type=document.file_type,
        status=document.status,
        error_message=document.error_message,
        chunk_count=chunk_count,
        created_at=document.created_at,
    )


@router.post("/documents", response_model=KnowledgeDocumentResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    上传知识库文档，并完成解析、切片、入库和向量写入。

    :param file: 用户上传的文档文件。
    :param current_user: 当前登录用户。
    :param db: 数据库会话。
    :return: 文档处理结果。
    """
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="仅支持 .txt 和 .md 文件")

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    saved_path = UPLOAD_DIR / f"{uuid4().hex}{suffix}"
    content = await file.read()
    saved_path.write_bytes(content)

    # 先落一条处理中记录，前端可以立即看到上传任务状态。
    document = KnowledgeDocument(
        user_id=current_user.id,
        name=file.filename or saved_path.name,
        file_type=suffix.lstrip("."),
        status="处理中",
    )
    db.add(document)
    db.commit()
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
                    "user_id": current_user.id,
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
        return _document_response(document, len(chunks))
    except Exception as exc:
        logger.exception(
            "知识库文档处理失败，document_id=%s, user_id=%s, filename=%s",
            document.id,
            current_user.id,
            file.filename,
        )
        db.rollback()
        try:
            # 如果 Qdrant 已写入但后续步骤失败，按 document_id 清理残留向量。
            delete_document_vectors(document.id, current_user.id)
        except Exception:
            logger.exception(
                "知识库文档处理失败后清理 Qdrant 向量失败，document_id=%s, user_id=%s",
                document.id,
                current_user.id,
            )
        document = db.get(KnowledgeDocument, document.id)
        # 失败只保留 document 记录和错误信息，不保留不完整的 chunk 数据。
        document.status = "失败"
        document.error_message = str(exc)
        db.add(document)
        db.commit()
        db.refresh(document)
        return _document_response(document, 0)


@router.get("/documents", response_model=KnowledgeDocumentListResponse)
def list_documents(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    获取当前用户的知识库文档列表。

    :param current_user: 当前登录用户。
    :param db: 数据库会话。
    :return: 文档列表响应。
    """
    documents = db.scalars(
        select(KnowledgeDocument)
        .where(KnowledgeDocument.user_id == current_user.id)
        .order_by(KnowledgeDocument.created_at.desc())
    ).all()
    counts = dict(
        db.execute(
            select(KnowledgeChunk.document_id, func.count(KnowledgeChunk.id))
            .group_by(KnowledgeChunk.document_id)
        ).all()
    )
    return KnowledgeDocumentListResponse(
        items=[_document_response(document, counts.get(document.id, 0)) for document in documents]
    )


@router.get("/documents/{document_id}", response_model=KnowledgeDocumentDetail)
def get_document(
    document_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    获取指定知识库文档详情和切片列表。

    :param document_id: 文档 ID。
    :param current_user: 当前登录用户。
    :param db: 数据库会话。
    :return: 文档详情响应。
    """
    document = db.scalar(
        select(KnowledgeDocument).where(
            KnowledgeDocument.id == document_id,
            KnowledgeDocument.user_id == current_user.id,
        )
    )
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文档不存在")

    chunks = db.scalars(
        select(KnowledgeChunk).where(KnowledgeChunk.document_id == document_id).order_by(KnowledgeChunk.id)
    ).all()
    base = _document_response(document, len(chunks))
    return KnowledgeDocumentDetail(
        **base.model_dump(),
        chunks=[KnowledgeChunkResponse.model_validate(chunk) for chunk in chunks],
    )


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(
    document_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    删除指定知识库文档及其切片和向量数据。

    :param document_id: 文档 ID。
    :param current_user: 当前登录用户。
    :param db: 数据库会话。
    :return: None。
    """
    document = db.scalar(
        select(KnowledgeDocument).where(
            KnowledgeDocument.id == document_id,
            KnowledgeDocument.user_id == current_user.id,
        )
    )
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文档不存在")

    # 删除文档时先删向量，再删 MySQL chunk，避免知识库检索命中已经删除的文档。
    delete_document_vectors(document_id, current_user.id)
    db.execute(delete(KnowledgeChunk).where(KnowledgeChunk.document_id == document_id))
    db.delete(document)
    db.commit()
