import json
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.database import SessionLocal, get_db
from app.models.chat import ChatMessage, ChatSession
from app.models.message_source import MessageSource
from app.models.usage import UserDailyQuestionUsage
from app.models.user import User
from app.schemas.chat import ChatQuotaResponse, ChatStreamRequest
from app.services.intent_service import classify_business_intent
from app.services.rag_service import rag_answer_stream

router = APIRouter(prefix="/chat", tags=["chat"])
logger = logging.getLogger(__name__)


DEFAULT_SESSION_TITLES = {"New chat", "新建对话"}


def _build_session_title(question: str) -> str:
    title = question.strip().replace("\n", " ")[:30]
    return title or "新建对话"


def _refresh_session_title_if_needed(session: ChatSession, question: str) -> None:
    if not session.title or session.title in DEFAULT_SESSION_TITLES:
        session.title = _build_session_title(question)


def _load_recent_history(db: Session, session_id: int, limit: int = 10) -> list[dict]:
    messages = db.scalars(
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc())
        .limit(limit)
    ).all()
    return [
        {
            "role": item.role,
            "content": item.content,
        }
        for item in reversed(messages)
    ]


def _get_daily_usage(db: Session, user_id: int, for_update: bool = False) -> UserDailyQuestionUsage | None:
    usage_date = datetime.now().date()
    statement = select(UserDailyQuestionUsage).where(
        UserDailyQuestionUsage.user_id == user_id,
        UserDailyQuestionUsage.usage_date == usage_date,
    )
    if for_update:
        statement = statement.with_for_update()
    return db.scalar(statement)


def _build_quota_response(used_count: int) -> ChatQuotaResponse:
    limit = settings.daily_question_limit
    if limit <= 0:
        return ChatQuotaResponse(limit=limit, used=used_count, remaining=-1, available=True)
    remaining = max(limit - used_count, 0)
    return ChatQuotaResponse(limit=limit, used=used_count, remaining=remaining, available=remaining > 0)


def _ensure_daily_question_quota(db: Session, user_id: int) -> None:
    if settings.daily_question_limit <= 0:
        return

    usage = _get_daily_usage(db, user_id, for_update=True)
    used_count = usage.question_count if usage else 0
    if used_count >= settings.daily_question_limit:
        logger.info(
            "每日提问次数已达上限，user_id=%s, used_count=%s, limit=%s",
            user_id,
            used_count,
            settings.daily_question_limit,
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"今日提问次数已达上限（{settings.daily_question_limit} 次），请明天再试。",
        )
    if usage is None:
        db.add(UserDailyQuestionUsage(user_id=user_id, usage_date=usage_date, question_count=1))
    else:
        usage.question_count += 1


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


@router.get("/quota", response_model=ChatQuotaResponse)
def get_chat_quota(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    usage = _get_daily_usage(db, current_user.id)
    used_count = usage.question_count if usage else 0
    return _build_quota_response(used_count)


@router.post("/stream")
async def stream_chat(
    payload: ChatStreamRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    current_user_id = current_user.id
    question = payload.question
    session = _get_or_create_session(payload, current_user, db)
    session_id = session.id
    history = _load_recent_history(db, session_id)

    _ensure_daily_question_quota(db, current_user_id)
    business_intent = classify_business_intent(question)
    user_message = ChatMessage(session_id=session_id, role="user", content=question, intent=business_intent)
    db.add(user_message)
    session.updated_at = datetime.now()
    db.commit()
    db.refresh(user_message)

    async def event_generator():
        assistant_parts: list[str] = []
        source_items: list[dict] = []

        yield "event: session\n"
        yield f"data: {json.dumps({'session_id': session_id, 'user_message_id': user_message.id, 'intent': business_intent}, ensure_ascii=False)}\n\n"

        async for event in rag_answer_stream(
            {
                "session_id": session_id,
                "user_id": current_user_id,
                "question": question,
                "history": history,
                "business_intent": business_intent,
            }
        ):
            if event["event"] == "message":
                data = event.get("data", {})
                if data.get("type") == "delta":
                    assistant_parts.append(data.get("content", ""))
            elif event["event"] == "source":
                source_items = event.get("data", {}).get("items", [])

            yield f"event: {event['event']}\n"
            yield f"data: {json.dumps(event['data'], ensure_ascii=False)}\n\n"

        assistant_content = "".join(assistant_parts).strip()
        if assistant_content:
            with SessionLocal() as stream_db:
                assistant_message = ChatMessage(session_id=session_id, role="assistant", content=assistant_content)
                stream_db.add(assistant_message)
                stream_db.execute(
                    update(ChatSession).where(ChatSession.id == session_id).values(updated_at=datetime.now())
                )
                stream_db.commit()
                stream_db.refresh(assistant_message)
                if source_items:
                    stream_db.add_all(
                        [
                            MessageSource(
                                message_id=assistant_message.id,
                                document_id=item.get("document_id") or 0,
                                chunk_id=item.get("chunk_id") or 0,
                                score=item.get("score"),
                                summary=item.get("summary"),
                                doc_name=item.get("doc_name"),
                            )
                            for item in source_items
                        ]
                    )
                    stream_db.commit()
                yield "event: saved\n"
                yield f"data: {json.dumps({'message_id': assistant_message.id}, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
