import logging
from pathlib import Path

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
from app.services.knowledge_import_service import (
    DuplicateKnowledgeDocumentError,
    KnowledgeDocumentProcessingError,
    SUPPORTED_SUFFIXES,
    import_knowledge_document,
)
from app.services.vector_service import delete_document_vectors

router = APIRouter(prefix="/knowledge", tags=["knowledge"])
logger = logging.getLogger(__name__)


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
        file_hash=document.file_hash,
        status=document.status,
        error_message=document.error_message,
        chunk_count=chunk_count,
        created_at=document.created_at,
    )


@router.post("/documents", response_model=KnowledgeDocumentResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: UploadFile = File(...),
    _current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    上传知识库文档，并完成解析、切片、入库和向量写入。

    :param file: 用户上传的文档文件。
    :param _current_user: 当前登录用户，仅用于鉴权。
    :param db: 数据库会话。
    :return: 文档处理结果。
    """
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="仅支持 .txt 和 .md 文件")

    content = await file.read()
    try:
        document, chunk_count, _skipped = import_knowledge_document(
            db,
            filename=file.filename or "",
            content=content,
            fail_on_duplicate=True,
        )
        return _document_response(document, chunk_count)
    except DuplicateKnowledgeDocumentError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="已存在相同内容的文档")
    except KnowledgeDocumentProcessingError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="相同文档正在处理中")


@router.get("/documents", response_model=KnowledgeDocumentListResponse)
def list_documents(
    _current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    获取企业共享知识库文档列表。

    :param _current_user: 当前登录用户，仅用于鉴权。
    :param db: 数据库会话。
    :return: 文档列表响应。
    """
    documents = db.scalars(select(KnowledgeDocument).order_by(KnowledgeDocument.created_at.desc())).all()
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
    _current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    获取指定知识库文档详情和切片列表。

    :param document_id: 文档 ID。
    :param _current_user: 当前登录用户，仅用于鉴权。
    :param db: 数据库会话。
    :return: 文档详情响应。
    """
    document = db.scalar(select(KnowledgeDocument).where(KnowledgeDocument.id == document_id))
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
    _current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    删除指定知识库文档及其切片和向量数据。

    :param document_id: 文档 ID。
    :param _current_user: 当前登录用户，仅用于鉴权。
    :param db: 数据库会话。
    :return: None。
    """
    document = db.scalar(select(KnowledgeDocument).where(KnowledgeDocument.id == document_id))
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文档不存在")

    # 删除文档时先删向量，再删 MySQL chunk，避免知识库检索命中已经删除的文档。
    delete_document_vectors(document_id)
    db.execute(delete(KnowledgeChunk).where(KnowledgeChunk.document_id == document_id))
    db.delete(document)
    db.commit()
