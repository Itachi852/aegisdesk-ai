import logging

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


def _is_placeholder_api_key() -> bool:
    """
    判断当前 Rerank API Key 是否仍是占位配置。

    :return: 是占位配置时返回 True。
    """
    api_key = settings.resolved_rerank_api_key
    return not api_key or api_key in {"replace-with-your-api-key", "replace-with-your-bailian-api-key"}


def rerank_chunks(question: str, chunks: list[dict], top_n: int | None = None) -> list[dict]:
    """
    调用 Rerank 服务对候选知识片段重新排序。

    :param question: 用户问题。
    :param chunks: 候选知识片段列表。
    :param top_n: 返回的最大片段数量。
    :return: 重排后的知识片段列表。
    """
    if not chunks:
        return []

    final_top_n = top_n or settings.rag_top_k
    if _is_placeholder_api_key():
        # Rerank 不是强依赖；未配置时直接沿用 RRF 排序，保证 RAG 链路可用。
        logger.warning("Rerank API Key 未配置，跳过 rerank，使用 RRF 排序结果。")
        return chunks[:final_top_n]

    payload = {
        "model": settings.rerank_model,
        "input": {
            "query": question,
            "documents": [item.get("content", "") for item in chunks],
        },
        "parameters": {
            "return_documents": False,
            "top_n": min(final_top_n, len(chunks)),
        },
    }
    headers = {
        "Authorization": f"Bearer {settings.resolved_rerank_api_key}",
        "Content-Type": "application/json",
    }

    try:
        with httpx.Client(timeout=httpx.Timeout(60.0, connect=10.0)) as client:
            response = client.post(settings.rerank_url, headers=headers, json=payload)
            response.raise_for_status()
    except Exception:
        # 外部重排服务失败时不阻断回答，只降级为召回阶段的排序。
        logger.exception("Rerank 调用失败，使用 RRF 排序结果。")
        return chunks[:final_top_n]

    data = response.json()
    results = data.get("output", {}).get("results", [])
    reranked: list[dict] = []
    for result in results:
        index = result.get("index")
        if not isinstance(index, int) or index < 0 or index >= len(chunks):
            continue
        item = dict(chunks[index])
        score = result.get("relevance_score")
        if score is not None:
            item["rerank_score"] = score
            item["score"] = round(float(score), 4)
        reranked.append(item)

    return reranked[:final_top_n] or chunks[:final_top_n]
