from datetime import datetime

from pydantic import BaseModel, Field


class SessionCreateRequest(BaseModel):
    title: str | None = Field(default=None, max_length=255)


class MessageSourceResponse(BaseModel):
    doc_name: str | None = None
    document_id: int | None = None
    chunk_id: int | None = None
    score: float | None = None
    summary: str | None = None


class ChatMessageResponse(BaseModel):
    id: int
    session_id: int
    role: str
    content: str
    intent: str | None = None
    feedback: str | None = None
    sources: list[MessageSourceResponse] = []
    created_at: datetime

    model_config = {"from_attributes": True}


class SessionListItem(BaseModel):
    id: int
    title: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class SessionDetail(SessionListItem):
    messages: list[ChatMessageResponse]


class SessionListResponse(BaseModel):
    items: list[SessionListItem]
