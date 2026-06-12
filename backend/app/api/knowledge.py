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

UPLOAD_DIR = Path("uploads/knowledge")
SUPPORTED_SUFFIXES = {".txt", ".md"}


def _document_response(document: KnowledgeDocument, chunk_count: int = 0) -> KnowledgeDocumentResponse:
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
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="仅支持 .txt 和 .md 文件")

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    saved_path = UPLOAD_DIR / f"{uuid4().hex}{suffix}"
    content = await file.read()
    saved_path.write_bytes(content)

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

        for chunk in chunk_models:
            chunk.vector_id = str(chunk.id)

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
        db.rollback()
        try:
            delete_document_vectors(document.id, current_user.id)
        except Exception:
            pass
        document = db.get(KnowledgeDocument, document.id)
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
    document = db.scalar(
        select(KnowledgeDocument).where(
            KnowledgeDocument.id == document_id,
            KnowledgeDocument.user_id == current_user.id,
        )
    )
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文档不存在")

    delete_document_vectors(document_id, current_user.id)
    db.execute(delete(KnowledgeChunk).where(KnowledgeChunk.document_id == document_id))
    db.delete(document)
    db.commit()
