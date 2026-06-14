from collections.abc import AsyncIterator, Sequence
from functools import lru_cache
import logging

from langchain_core.messages import BaseMessage, HumanMessage
from langchain_openai import ChatOpenAI

from app.core.config import settings

logger = logging.getLogger(__name__)
LLM_FAILED_MESSAGE = "抱歉，当前暂时无法生成回答，请稍后再试。"


def _is_placeholder_api_key() -> bool:
    return not settings.llm_api_key or settings.llm_api_key == "replace-with-your-api-key"


@lru_cache(maxsize=1)
def get_chat_model() -> ChatOpenAI:
    return ChatOpenAI(
        model=settings.llm_model,
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        temperature=0.2,
        streaming=True,
        timeout=60,
        max_retries=2,
    )


@lru_cache(maxsize=1)
def get_intent_model() -> ChatOpenAI:
    return ChatOpenAI(
        model=settings.llm_model,
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        temperature=0,
        streaming=False,
        timeout=30,
        max_retries=1,
    )


def _to_messages(prompt: str | Sequence[BaseMessage]) -> list[BaseMessage]:
    if isinstance(prompt, str):
        return [HumanMessage(content=prompt)]
    return list(prompt)


def _content_to_text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(str(item.get("text", "")) for item in content if isinstance(item, dict))
    return str(content or "")


async def invoke_llm_text(prompt: str | Sequence[BaseMessage]) -> str:
    if _is_placeholder_api_key():
        raise RuntimeError("模型 API Key 未配置，请先在 .env 中填写 LLM_API_KEY。")

    response = await get_intent_model().ainvoke(_to_messages(prompt))
    return _content_to_text(response.content).strip()


async def stream_llm(prompt: str | Sequence[BaseMessage]) -> AsyncIterator[str]:
    if _is_placeholder_api_key():
        logger.warning("LLM_API_KEY 未配置，无法调用模型。")
        yield LLM_FAILED_MESSAGE
        return

    try:
        async for chunk in get_chat_model().astream(_to_messages(prompt)):
            text = _content_to_text(chunk.content)
            if text:
                yield text
    except Exception as exc:
        logger.exception("LLM 流式调用失败。")
        yield LLM_FAILED_MESSAGE
