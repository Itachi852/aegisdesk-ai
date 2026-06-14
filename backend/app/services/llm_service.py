from collections.abc import AsyncIterator, Sequence
from functools import lru_cache
import logging

from langchain_core.messages import BaseMessage, HumanMessage
from langchain_openai import ChatOpenAI

from app.core.config import settings

logger = logging.getLogger(__name__)
LLM_FAILED_MESSAGE = "抱歉，当前暂时无法生成回答，请稍后再试。"


def _is_placeholder_api_key() -> bool:
    """
    判断当前 LLM API Key 是否仍是占位配置。

    :return: 是占位配置时返回 True。
    """
    return not settings.llm_api_key or settings.llm_api_key == "replace-with-your-api-key"


@lru_cache(maxsize=1)
def get_chat_model() -> ChatOpenAI:
    """
    获取用于生成回答的大模型客户端。

    :return: 支持流式输出的 ChatOpenAI 实例。
    """
    # 主回答模型开启 streaming，用于聊天页面逐字/逐段输出。
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
    """
    获取用于意图识别和问题改写的大模型客户端。

    :return: 非流式 ChatOpenAI 实例。
    """
    # 意图识别和问题改写需要稳定短文本结果，所以关闭 streaming 并降低 temperature。
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
    """
    将字符串或消息序列统一转换为 LangChain 消息列表。

    :param prompt: 文本提示词或 BaseMessage 序列。
    :return: BaseMessage 消息列表。
    """
    if isinstance(prompt, str):
        return [HumanMessage(content=prompt)]
    return list(prompt)


def _content_to_text(content) -> str:
    """
    将模型返回的 content 转换为纯文本。

    :param content: 模型返回内容。
    :return: 文本内容。
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(str(item.get("text", "")) for item in content if isinstance(item, dict))
    return str(content or "")


async def invoke_llm_text(prompt: str | Sequence[BaseMessage]) -> str:
    """
    调用非流式大模型并返回完整文本。

    :param prompt: 文本提示词或消息列表。
    :return: 模型生成的完整文本。
    """
    if _is_placeholder_api_key():
        raise RuntimeError("模型 API Key 未配置，请先在 .env 中填写 LLM_API_KEY。")

    response = await get_intent_model().ainvoke(_to_messages(prompt))
    return _content_to_text(response.content).strip()


async def stream_llm(prompt: str | Sequence[BaseMessage]) -> AsyncIterator[str]:
    """
    流式调用大模型并逐段返回文本。

    :param prompt: 文本提示词或消息列表。
    :return: 模型输出文本的异步迭代器。
    """
    if _is_placeholder_api_key():
        logger.warning("LLM_API_KEY 未配置，无法调用模型。")
        yield LLM_FAILED_MESSAGE
        return

    try:
        # 只向前端暴露自然语言兜底提示，详细异常写入后端日志，避免影响用户体验。
        async for chunk in get_chat_model().astream(_to_messages(prompt)):
            text = _content_to_text(chunk.content)
            if text:
                yield text
    except Exception as exc:
        logger.exception("LLM 流式调用失败。")
        yield LLM_FAILED_MESSAGE
