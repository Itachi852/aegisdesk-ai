from functools import lru_cache

from langchain_openai import OpenAIEmbeddings

from app.core.config import settings


def _embeddings_url() -> str:
    """
    生成 Embedding 接口地址。

    :return: 以 /embeddings 结尾的接口地址。
    """
    base_url = settings.resolved_embedding_base_url.rstrip("/")
    if base_url.endswith("/embeddings"):
        return base_url
    return f"{base_url}/embeddings"


def _is_placeholder_api_key() -> bool:
    """
    判断当前 Embedding API Key 是否仍是占位配置。

    :return: 是占位配置时返回 True。
    """
    api_key = settings.resolved_embedding_api_key
    return not api_key or api_key in {"replace-with-your-api-key", "replace-with-your-embedding-api-key"}


@lru_cache(maxsize=1)
def get_embeddings_model() -> OpenAIEmbeddings:
    """
    获取 Embedding 模型客户端。

    :return: OpenAI 兼容的 Embedding 客户端。
    """
    # 使用 OpenAI 兼容协议，百炼/通义等服务只需要通过 .env 切换 base_url、key 和模型名。
    return OpenAIEmbeddings(
        model=settings.embedding_model,
        api_key=settings.resolved_embedding_api_key,
        base_url=settings.resolved_embedding_base_url,
        max_retries=3,
        timeout=60,
        check_embedding_ctx_length=False,
    )


def _normalize_embedding_error(exc: Exception) -> RuntimeError:
    """
    将底层 Embedding 异常转换为更易读的业务异常。

    :param exc: 底层异常对象。
    :return: 标准化后的 RuntimeError。
    """
    # 对外抛出可读的业务错误，同时用 raise ... from exc 保留底层异常链方便日志排查。
    message = str(exc)
    if "401" in message or "Unauthorized" in message:
        return RuntimeError("Embedding 认证失败，请检查 EMBEDDING_API_KEY 是否正确。")
    if "429" in message or "rate" in message.lower() or "quota" in message.lower():
        return RuntimeError(f"Embedding 服务限流或额度不足：{message[:300]}")
    if "timeout" in message.lower() or "connect" in message.lower():
        return RuntimeError("Embedding 服务连接失败或超时，请检查 EMBEDDING_BASE_URL 和网络。")
    return RuntimeError(f"Embedding 服务调用失败：{message[:300]}")


def embed_text(text: str) -> list[float]:
    """
    将单段文本转换为向量。

    :param text: 待向量化文本。
    :return: 文本向量。
    """
    return embed_texts([text])[0]


def embed_texts(texts: list[str]) -> list[list[float]]:
    """
    批量将文本转换为向量。

    :param texts: 待向量化文本列表。
    :return: 文本向量列表。
    """
    if not texts:
        return []
    if _is_placeholder_api_key():
        raise RuntimeError("Embedding API Key 未配置，请在 .env 中填写 EMBEDDING_API_KEY 或 LLM_API_KEY。")

    try:
        return get_embeddings_model().embed_documents(texts)
    except Exception as exc:
        raise _normalize_embedding_error(exc) from exc
