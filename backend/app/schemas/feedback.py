from pydantic import BaseModel, Field


class FeedbackCreateRequest(BaseModel):
    message_id: int
    rating: str = Field(pattern="^(like|dislike)$")
    comment: str | None = Field(default=None, max_length=500)


class FeedbackResponse(BaseModel):
    id: int
    message_id: int
    rating: str
    comment: str | None = None

    model_config = {"from_attributes": True}
