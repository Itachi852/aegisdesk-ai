from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, desc, select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.chat import ChatMessage, ChatSession
from app.models.feedback import Feedback
from app.models.message_source import MessageSource
from app.models.user import User
from app.schemas.session import (
    ChatMessageResponse,
    MessageSourceResponse,
    SessionCreateRequest,
    SessionDetail,
    SessionListResponse,
)

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.post("", response_model=SessionDetail, status_code=status.HTTP_201_CREATED)
def create_session(
    payload: SessionCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    session = ChatSession(user_id=current_user.id, title=payload.title or "新建对话")
    db.add(session)
    db.commit()
    db.refresh(session)
    return SessionDetail.model_validate(session)


@router.get("", response_model=SessionListResponse)
def list_sessions(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    sessions = db.scalars(
        select(ChatSession)
        .where(ChatSession.user_id == current_user.id)
        .order_by(desc(ChatSession.updated_at), desc(ChatSession.id))
    ).all()
    return SessionListResponse(items=sessions)


@router.get("/{session_id}", response_model=SessionDetail)
def get_session(
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    session = db.scalar(
        select(ChatSession)
        .options(selectinload(ChatSession.messages))
        .where(ChatSession.id == session_id, ChatSession.user_id == current_user.id)
    )
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    message_ids = [item.id for item in session.messages if item.role == "assistant"]
    feedback_by_message_id: dict[int, str] = {}
    sources_by_message_id: dict[int, list[MessageSourceResponse]] = {}
    if message_ids:
        feedback_rows = db.scalars(
            select(Feedback)
            .where(Feedback.user_id == current_user.id, Feedback.message_id.in_(message_ids))
            .order_by(Feedback.message_id, desc(Feedback.id))
        ).all()
        for item in feedback_rows:
            feedback_by_message_id.setdefault(item.message_id, item.rating)

        source_rows = db.scalars(
            select(MessageSource)
            .where(MessageSource.message_id.in_(message_ids))
            .order_by(MessageSource.message_id, MessageSource.id)
        ).all()
        for item in source_rows:
            sources_by_message_id.setdefault(item.message_id, []).append(
                MessageSourceResponse(
                    doc_name=item.doc_name,
                    document_id=item.document_id,
                    chunk_id=item.chunk_id,
                    score=float(item.score) if item.score is not None else None,
                    summary=item.summary,
                )
            )

    return SessionDetail(
        id=session.id,
        title=session.title,
        created_at=session.created_at,
        updated_at=session.updated_at,
        messages=[
            ChatMessageResponse(
                id=item.id,
                session_id=item.session_id,
                role=item.role,
                content=item.content,
                intent=item.intent,
                feedback=feedback_by_message_id.get(item.id),
                sources=sources_by_message_id.get(item.id, []),
                created_at=item.created_at,
            )
            for item in session.messages
        ],
    )


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_session(
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    session = db.scalar(
        select(ChatSession).where(ChatSession.id == session_id, ChatSession.user_id == current_user.id)
    )
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    message_ids = db.scalars(select(ChatMessage.id).where(ChatMessage.session_id == session_id)).all()
    if message_ids:
        db.execute(delete(MessageSource).where(MessageSource.message_id.in_(message_ids)))
        db.execute(delete(Feedback).where(Feedback.message_id.in_(message_ids)))
    db.execute(delete(ChatMessage).where(ChatMessage.session_id == session_id))
    db.delete(session)
    db.commit()
