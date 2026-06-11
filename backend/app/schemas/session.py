from datetime import datetime

from pydantic import BaseModel, Field


class SessionCreateRequest(BaseModel):
    title: str | None = Field(default=None, max_length=255)


class ChatMessageResponse(BaseModel):
    id: int
    session_id: int
    role: str
    content: str
    intent: str | None = None
    feedback: str | None = None
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
