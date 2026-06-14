from functools import lru_cache

from langchain_openai import OpenAIEmbeddings

from app.core.config import settings


def _embeddings_url() -> str:
    base_url = settings.resolved_embedding_base_url.rstrip("/")
    if base_url.endswith("/embeddings"):
        return base_url
    return f"{base_url}/embeddings"


def _is_placeholder_api_key() -> bool:
    api_key = settings.resolved_embedding_api_key
    return not api_key or api_key in {"replace-with-your-api-key", "replace-with-your-embedding-api-key"}


@lru_cache(maxsize=1)
def get_embeddings_model() -> OpenAIEmbeddings:
    return OpenAIEmbeddings(
        model=settings.embedding_model,
        api_key=settings.resolved_embedding_api_key,
        base_url=settings.resolved_embedding_base_url,
        max_retries=3,
        timeout=60,
        check_embedding_ctx_length=False,
    )


def _normalize_embedding_error(exc: Exception) -> RuntimeError:
    message = str(exc)
    if "401" in message or "Unauthorized" in message:
        return RuntimeError("Embedding 认证失败，请检查 EMBEDDING_API_KEY 是否正确。")
    if "429" in message or "rate" in message.lower() or "quota" in message.lower():
        return RuntimeError(f"Embedding 服务限流或额度不足：{message[:300]}")
    if "timeout" in message.lower() or "connect" in message.lower():
        return RuntimeError("Embedding 服务连接失败或超时，请检查 EMBEDDING_BASE_URL 和网络。")
    return RuntimeError(f"Embedding 服务调用失败：{message[:300]}")


def embed_text(text: str) -> list[float]:
    return embed_texts([text])[0]


def embed_texts(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    if _is_placeholder_api_key():
        raise RuntimeError("Embedding API Key 未配置，请在 .env 中填写 EMBEDDING_API_KEY 或 LLM_API_KEY。")

    try:
        return get_embeddings_model().embed_documents(texts)
    except Exception as exc:
        raise _normalize_embedding_error(exc) from exc
