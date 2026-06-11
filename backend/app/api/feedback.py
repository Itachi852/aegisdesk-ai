from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.chat import ChatMessage, ChatSession
from app.models.feedback import Feedback
from app.models.user import User
from app.schemas.feedback import FeedbackCreateRequest, FeedbackResponse

router = APIRouter(prefix="/feedback", tags=["feedback"])


@router.post("", response_model=FeedbackResponse, status_code=status.HTTP_201_CREATED)
def submit_feedback(
    payload: FeedbackCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    message = db.scalar(
        select(ChatMessage)
        .join(ChatSession, ChatSession.id == ChatMessage.session_id)
        .where(
            ChatMessage.id == payload.message_id,
            ChatMessage.role == "assistant",
            ChatSession.user_id == current_user.id,
        )
    )
    if message is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI message not found")

    feedback = db.scalar(
        select(Feedback)
        .where(Feedback.message_id == payload.message_id, Feedback.user_id == current_user.id)
        .order_by(Feedback.id.desc())
    )
    if feedback is None:
        feedback = Feedback(message_id=payload.message_id, user_id=current_user.id, rating=payload.rating)
        db.add(feedback)

    feedback.rating = payload.rating
    feedback.comment = payload.comment.strip() if payload.comment else None
    db.add(feedback)
    db.commit()
    db.refresh(feedback)
    return FeedbackResponse.model_validate(feedback)
