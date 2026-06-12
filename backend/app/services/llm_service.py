import json
from collections.abc import AsyncIterator

import httpx

from app.core.config import settings


def _chat_completions_url() -> str:
    base_url = settings.llm_base_url.rstrip("/")
    if base_url.endswith("/chat/completions"):
        return base_url
    return f"{base_url}/chat/completions"


def _is_placeholder_api_key() -> bool:
    return not settings.llm_api_key or settings.llm_api_key == "replace-with-your-api-key"


async def stream_llm(prompt: str) -> AsyncIterator[str]:
    if _is_placeholder_api_key():
        yield "模型 API Key 未配置，请先在 .env 中填写 LLM_API_KEY。"
        return

    payload = {
        "model": settings.llm_model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": True,
        "temperature": 0.2,
    }
    headers = {
        "Authorization": f"Bearer {settings.llm_api_key}",
        "Content-Type": "application/json",
    }

    try:
        timeout = httpx.Timeout(60.0, connect=10.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream("POST", _chat_completions_url(), headers=headers, json=payload) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue

                    data = line.removeprefix("data:").strip()
                    if not data or data == "[DONE]":
                        continue

                    chunk = json.loads(data)
                    choices = chunk.get("choices") or []
                    if not choices:
                        continue

                    delta = choices[0].get("delta") or {}
                    content = delta.get("content")
                    if content:
                        yield content
    except httpx.HTTPStatusError as exc:
        status_code = exc.response.status_code
        if status_code == 401:
            yield "模型认证失败，请检查 LLM_API_KEY 是否正确。"
        elif status_code == 429:
            yield "模型服务请求过于频繁，请稍后再试。"
        else:
            yield f"模型服务返回异常，状态码：{status_code}。"
    except (httpx.TimeoutException, httpx.NetworkError):
        yield "模型服务连接失败或超时，请检查 LLM_BASE_URL 和网络。"
    except Exception:
        yield "模型调用失败，请检查后端日志。"
