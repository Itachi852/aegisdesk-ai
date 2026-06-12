from datetime import datetime

from pydantic import BaseModel


class KnowledgeDocumentResponse(BaseModel):
    id: int
    name: str
    file_type: str
    status: str
    error_message: str | None = None
    chunk_count: int = 0
    created_at: datetime


class KnowledgeDocumentListResponse(BaseModel):
    items: list[KnowledgeDocumentResponse]


class KnowledgeChunkResponse(BaseModel):
    id: int
    document_id: int
    content: str
    summary: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class KnowledgeDocumentDetail(KnowledgeDocumentResponse):
    chunks: list[KnowledgeChunkResponse]
