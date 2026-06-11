from pydantic import BaseModel, Field


class ChatStreamRequest(BaseModel):
    question: str = Field(min_length=1, max_length=500)
    session_id: int | None = None
