import json

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import SessionLocal, get_db
from app.models.chat import ChatMessage, ChatSession
from app.models.user import User
from app.schemas.chat import ChatStreamRequest
from app.services.rag_service import rag_answer_stream

router = APIRouter(prefix="/chat", tags=["chat"])


DEFAULT_SESSION_TITLES = {"New chat", "新建对话"}


def _build_session_title(question: str) -> str:
    title = question.strip().replace("\n", " ")[:30]
    return title or "新建对话"


def _refresh_session_title_if_needed(session: ChatSession, question: str) -> None:
    if not session.title or session.title in DEFAULT_SESSION_TITLES:
        session.title = _build_session_title(question)


def _get_or_create_session(
    payload: ChatStreamRequest,
    current_user: User,
    db: Session,
) -> ChatSession:
    if payload.session_id is None:
        title = _build_session_title(payload.question)
        session = ChatSession(user_id=current_user.id, title=title)
        db.add(session)
        db.commit()
        db.refresh(session)
        return session

    session = db.scalar(
        select(ChatSession).where(
            ChatSession.id == payload.session_id,
            ChatSession.user_id == current_user.id,
        )
    )
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    _refresh_session_title_if_needed(session, payload.question)
    return session


@router.post("/stream")
async def stream_chat(
    payload: ChatStreamRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    session = _get_or_create_session(payload, current_user, db)
    session_id = session.id

    user_message = ChatMessage(session_id=session_id, role="user", content=payload.question)
    db.add(user_message)
    db.commit()

    async def event_generator():
        assistant_parts: list[str] = []

        yield "event: session\n"
        yield f"data: {json.dumps({'session_id': session_id}, ensure_ascii=False)}\n\n"

        async for event in rag_answer_stream(
            {
                "session_id": session_id,
                "user_id": current_user.id,
                "question": payload.question,
            }
        ):
            if event["event"] == "message":
                data = event.get("data", {})
                if data.get("type") == "delta":
                    assistant_parts.append(data.get("content", ""))

            yield f"event: {event['event']}\n"
            yield f"data: {json.dumps(event['data'], ensure_ascii=False)}\n\n"

        assistant_content = "".join(assistant_parts).strip()
        if assistant_content:
            with SessionLocal() as stream_db:
                assistant_message = ChatMessage(session_id=session_id, role="assistant", content=assistant_content)
                stream_db.add(assistant_message)
                stream_db.commit()
                stream_db.refresh(assistant_message)
                yield "event: saved\n"
                yield f"data: {json.dumps({'message_id': assistant_message.id}, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
