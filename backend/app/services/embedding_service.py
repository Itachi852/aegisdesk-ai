import time

import httpx

from app.core.config import settings

MAX_EMBEDDING_RETRIES = 3


def _embeddings_url() -> str:
    base_url = settings.resolved_embedding_base_url.rstrip("/")
    if base_url.endswith("/embeddings"):
        return base_url
    return f"{base_url}/embeddings"


def _is_placeholder_api_key() -> bool:
    api_key = settings.resolved_embedding_api_key
    return not api_key or api_key in {"replace-with-your-api-key", "replace-with-your-embedding-api-key"}


def _response_error_message(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return response.text[:300]

    error = body.get("error")
    if isinstance(error, dict):
        return str(error.get("message") or error)
    return str(body)[:300]


def _request_embeddings(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    if _is_placeholder_api_key():
        raise RuntimeError("Embedding API Key 未配置，请在 .env 中填写 EMBEDDING_API_KEY 或 LLM_API_KEY。")

    payload = {
        "model": settings.embedding_model,
        "input": texts,
    }
    headers = {
        "Authorization": f"Bearer {settings.resolved_embedding_api_key}",
        "Content-Type": "application/json",
    }
    timeout = httpx.Timeout(60.0, connect=10.0)

    last_response: httpx.Response | None = None
    with httpx.Client(timeout=timeout) as client:
        for attempt in range(MAX_EMBEDDING_RETRIES + 1):
            try:
                response = client.post(_embeddings_url(), headers=headers, json=payload)
                last_response = response
                response.raise_for_status()
                break
            except httpx.HTTPStatusError as exc:
                status_code = exc.response.status_code
                if status_code == 429 and attempt < MAX_EMBEDDING_RETRIES:
                    retry_after = exc.response.headers.get("retry-after")
                    wait_seconds = float(retry_after) if retry_after else 2**attempt
                    time.sleep(min(wait_seconds, 8))
                    continue

                detail = _response_error_message(exc.response)
                if status_code == 401:
                    raise RuntimeError("Embedding 认证失败，请检查 EMBEDDING_API_KEY 是否正确。") from exc
                if status_code == 429:
                    raise RuntimeError(f"Embedding 服务限流或额度不足：{detail}") from exc
                raise RuntimeError(f"Embedding 服务返回异常，状态码：{status_code}，详情：{detail}") from exc
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                if attempt < MAX_EMBEDDING_RETRIES:
                    time.sleep(2**attempt)
                    continue
                raise RuntimeError("Embedding 服务连接失败或超时，请检查 EMBEDDING_BASE_URL 和网络。") from exc
        else:
            raise RuntimeError("Embedding 服务调用失败，请稍后重试。")

    if last_response is None:
        raise RuntimeError("Embedding 服务调用失败，请稍后重试。")

    result = last_response.json()
    data = sorted(result.get("data", []), key=lambda item: item.get("index", 0))
    vectors = [item.get("embedding") for item in data]
    if len(vectors) != len(texts) or any(vector is None for vector in vectors):
        raise RuntimeError("Embedding 服务返回格式不正确。")
    return vectors


def embed_text(text: str) -> list[float]:
    return _request_embeddings([text])[0]


def embed_texts(texts: list[str]) -> list[list[float]]:
    return _request_embeddings(texts)
