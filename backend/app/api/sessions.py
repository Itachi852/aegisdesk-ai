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
    """
    创建一个新的聊天会话。

    :param payload: 会话创建请求。
    :param current_user: 当前登录用户。
    :param db: 数据库会话。
    :return: 新创建的会话详情。
    """
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
    """
    获取当前用户的历史会话列表。

    :param current_user: 当前登录用户。
    :param db: 数据库会话。
    :return: 会话列表响应。
    """
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
    """
    获取指定会话的消息、反馈和引用来源。

    :param session_id: 会话 ID。
    :param current_user: 当前登录用户。
    :param db: 数据库会话。
    :return: 会话详情响应。
    """
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
        # 反馈只针对 AI 消息，历史会话加载时按 message_id 合并回消息列表。
        feedback_rows = db.scalars(
            select(Feedback)
            .where(Feedback.user_id == current_user.id, Feedback.message_id.in_(message_ids))
            .order_by(Feedback.message_id, desc(Feedback.id))
        ).all()
        for item in feedback_rows:
            feedback_by_message_id.setdefault(item.message_id, item.rating)

        # 引用来源按 chunk 存多条，前端展示时再按 document_id 去重。
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
    """
    删除指定聊天会话及其关联消息、反馈和引用来源。

    :param session_id: 会话 ID。
    :param current_user: 当前登录用户。
    :param db: 数据库会话。
    :return: None。
    """
    session = db.scalar(
        select(ChatSession).where(ChatSession.id == session_id, ChatSession.user_id == current_user.id)
    )
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    message_ids = db.scalars(select(ChatMessage.id).where(ChatMessage.session_id == session_id)).all()
    if message_ids:
        # 先删依赖消息的引用和反馈，再删消息和会话，避免外键残留。
        db.execute(delete(MessageSource).where(MessageSource.message_id.in_(message_ids)))
        db.execute(delete(Feedback).where(Feedback.message_id.in_(message_ids)))
    db.execute(delete(ChatMessage).where(ChatMessage.session_id == session_id))
    db.delete(session)
    db.commit()
