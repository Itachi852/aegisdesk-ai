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
    """
    根据用户首个问题生成会话标题。

    :param question: 用户输入的问题。
    :return: 截断后的会话标题。
    """
    title = question.strip().replace("\n", " ")[:30]
    return title or "新建对话"


def _refresh_session_title_if_needed(session: ChatSession, question: str) -> None:
    """
    在会话仍是默认标题时，用当前问题刷新标题。

    :param session: 当前聊天会话。
    :param question: 用户输入的问题。
    :return: None。
    """
    if not session.title or session.title in DEFAULT_SESSION_TITLES:
        session.title = _build_session_title(question)


def _load_recent_history(db: Session, session_id: int, limit: int = 10) -> list[dict]:
    """
    加载最近的历史消息，作为大模型上下文。

    :param db: 数据库会话。
    :param session_id: 聊天会话 ID。
    :param limit: 最多加载的消息数量。
    :return: 按时间正序排列的历史消息列表。
    """
    # 在保存本轮用户问题前读取历史，避免当前问题被重复塞进大模型上下文。
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
    """
    查询用户当天的提问额度使用记录。

    :param db: 数据库会话。
    :param user_id: 当前用户 ID。
    :param for_update: 是否对记录加行锁。
    :return: 当天使用记录，不存在时返回 None。
    """
    usage_date = datetime.now().date()
    statement = select(UserDailyQuestionUsage).where(
        UserDailyQuestionUsage.user_id == user_id,
        UserDailyQuestionUsage.usage_date == usage_date,
    )
    if for_update:
        # 并发发送时锁定当天用量行，防止多个请求同时通过额度检查。
        statement = statement.with_for_update()
    return db.scalar(statement)


def _build_quota_response(used_count: int) -> ChatQuotaResponse:
    """
    根据已使用次数构造前端需要的额度响应。

    :param used_count: 今日已提问次数。
    :return: 提问额度响应对象。
    """
    limit = settings.daily_question_limit
    if limit <= 0:
        return ChatQuotaResponse(limit=limit, used=used_count, remaining=-1, available=True)
    remaining = max(limit - used_count, 0)
    return ChatQuotaResponse(limit=limit, used=used_count, remaining=remaining, available=remaining > 0)


def _ensure_daily_question_quota(db: Session, user_id: int) -> None:
    """
    校验并扣减用户每日提问额度。

    :param db: 数据库会话。
    :param user_id: 当前用户 ID。
    :return: None。
    """
    if settings.daily_question_limit <= 0:
        return

    # 额度统计独立于聊天消息，用户删除会话后也不能绕过每日提问上限。
    usage_date = datetime.now().date()
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
    """
    获取已有会话，或在未传 session_id 时创建新会话。

    :param payload: 聊天请求参数。
    :param current_user: 当前登录用户。
    :param db: 数据库会话。
    :return: 当前聊天会话。
    """
    if payload.session_id is None:
        # 未指定 session_id 时，由后端自动创建会话，首个问题会同步作为默认标题。
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
    """
    获取当前用户今日提问额度。

    :param current_user: 当前登录用户。
    :param db: 数据库会话。
    :return: 今日额度使用情况。
    """
    usage = _get_daily_usage(db, current_user.id)
    used_count = usage.question_count if usage else 0
    return _build_quota_response(used_count)


@router.post("/stream")
async def stream_chat(
    payload: ChatStreamRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    处理流式聊天请求，并在流结束后保存 AI 回复。

    :param payload: 聊天请求参数。
    :param current_user: 当前登录用户。
    :param db: 数据库会话。
    :return: SSE 流式响应。
    """
    # StreamingResponse 会在接口返回后继续迭代，先取出标量 ID，避免后续使用已关闭的 ORM 对象。
    current_user_id = current_user.id
    question = payload.question
    session = _get_or_create_session(payload, current_user, db)
    session_id = session.id
    history = _load_recent_history(db, session_id)

    _ensure_daily_question_quota(db, current_user_id)
    # 业务意图先用本地规则标注到用户消息，供前端展示和后续 RAG 提示词使用。
    business_intent = classify_business_intent(question)
    user_message = ChatMessage(session_id=session_id, role="user", content=question, intent=business_intent)
    db.add(user_message)
    session.updated_at = datetime.now()
    db.commit()
    db.refresh(user_message)

    async def event_generator():
        """
        生成聊天 SSE 事件。

        :return: SSE 事件异步迭代器。
        """
        assistant_parts: list[str] = []
        source_items: list[dict] = []

        # session 事件让前端把临时用户消息替换为数据库中的真实消息 ID 和意图标签。
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
                    # 逐段收集模型输出，流结束后一次性保存完整 AI 消息。
                    assistant_parts.append(data.get("content", ""))
            elif event["event"] == "source":
                source_items = event.get("data", {}).get("items", [])

            yield f"event: {event['event']}\n"
            yield f"data: {json.dumps(event['data'], ensure_ascii=False)}\n\n"

        assistant_content = "".join(assistant_parts).strip()
        if assistant_content:
            # 流式响应期间原请求的 db 依赖可能已经结束，这里使用新的短生命周期会话写库。
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
