import json
import logging
from typing import Any, Literal, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph import END, START, StateGraph

from app.core.config import settings
from app.prompts.qa_prompt import (
    build_chat_messages,
    build_intent_messages,
    build_no_knowledge_messages,
    build_qa_messages,
    build_query_rewrite_messages,
)
from app.services.intent_service import get_business_intent_keywords
from app.services.llm_service import invoke_llm_text, stream_llm
from app.services.rerank_service import rerank_chunks
from app.services.vector_service import search_chunks

ANSWER_FAILED_MESSAGE = "抱歉，当前暂时无法生成回答，请稍后再试。"
Intent = Literal["knowledge_qa", "general_chat"]
logger = logging.getLogger(__name__)


class RagState(TypedDict, total=False):
    session_id: int
    user_id: int
    question: str
    history: list[dict]
    business_intent: str
    intent: Intent
    queries: list[str]
    candidates: list[dict]
    fused_chunks: list[dict]
    chunks: list[dict]
    messages: list[BaseMessage]
    error: str


def _dedupe_queries(question: str, rewritten_queries: list[str]) -> list[str]:
    queries: list[str] = []
    seen: set[str] = set()
    for item in [question, *rewritten_queries]:
        query = item.strip()
        if not query or query in seen:
            continue
        seen.add(query)
        queries.append(query)
    return queries[: settings.rag_rewrite_query_count + 1]


def _candidate_key(item: dict) -> str:
    return str(item.get("chunk_id") or f"{item.get('document_id')}:{item.get('content', '')[:80]}")


def _parse_rewrite_queries(text: str) -> list[str]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`").strip()
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:].strip()
    start = cleaned.find("[")
    end = cleaned.rfind("]")
    if start >= 0 and end >= start:
        cleaned = cleaned[start : end + 1]

    result = json.loads(cleaned)
    if not isinstance(result, list):
        raise ValueError("query rewrite result is not a list")
    return [str(item) for item in result]


def _rrf_fuse(candidates: list[dict]) -> list[dict]:
    grouped: dict[str, dict] = {}
    for item in candidates:
        key = _candidate_key(item)
        rank = int(item.get("rank") or 999)
        contribution = 1.0 / (settings.rag_rrf_k + rank)
        current = grouped.get(key)
        if current is None:
            current = dict(item)
            current["score"] = 0.0
            current["queries"] = []
            current["query_ranks"] = []
            grouped[key] = current

        current["score"] += contribution
        if item.get("query") not in current["queries"]:
            current["queries"].append(item.get("query"))
        current["query_ranks"].append({"query": item.get("query"), "rank": rank})

    fused = list(grouped.values())
    fused.sort(key=lambda item: item["score"], reverse=True)
    for item in fused:
        item["score"] = round(float(item["score"]), 6)
    return fused[: settings.rag_rrf_top_k]


def _filter_relevant_chunks(question: str, business_intent: str, chunks: list[dict]) -> list[dict]:
    if not chunks:
        return []

    reranked_chunks = [item for item in chunks if item.get("rerank_score") is not None]
    if reranked_chunks:
        return [
            item
            for item in reranked_chunks
            if float(item.get("rerank_score") or 0) >= settings.rag_score_threshold
        ][: settings.rag_top_k]

    intent_keywords = get_business_intent_keywords(business_intent)
    if not intent_keywords:
        return chunks[: settings.rag_top_k]

    relevant_chunks = [
        item
        for item in chunks
        if any(keyword in item.get("content", "") or keyword in item.get("summary", "") for keyword in intent_keywords)
    ]
    if relevant_chunks:
        return relevant_chunks[: settings.rag_top_k]

    logger.info(
        "召回片段未命中业务意图关键词，清空引用，business_intent=%s, question=%s",
        business_intent,
        question,
    )
    return []


async def validate_question(state: RagState) -> dict[str, Any]:
    question = (state.get("question") or "").strip()
    if len(question) > settings.max_question_length:
        return {"error": "单次提问不能超过 500 字"}
    return {"question": question}


async def classify_intent(state: RagState) -> dict[str, Any]:
    if state.get("error"):
        return {}

    question = state.get("question", "")
    history = state.get("history", [])
    try:
        result = await invoke_llm_text(build_intent_messages(question=question, history=history))
        normalized = result.strip().lower()
        if "general_chat" in normalized:
            return {"intent": "general_chat"}
        if "knowledge_qa" in normalized:
            return {"intent": "knowledge_qa"}

        logger.warning("意图识别返回了未知标签，按 knowledge_qa 处理：%s", result)
        return {"intent": "knowledge_qa"}
    except Exception:
        logger.exception(
            "意图识别失败，按 knowledge_qa 处理，session_id=%s, user_id=%s, question=%s",
            state.get("session_id"),
            state.get("user_id"),
            question,
        )
        return {"intent": "knowledge_qa"}


async def rewrite_queries(state: RagState) -> dict[str, Any]:
    if state.get("error") or state.get("intent") == "general_chat":
        return {"queries": []}

    question = state.get("question", "")
    history = state.get("history", [])
    try:
        result = await invoke_llm_text(
            build_query_rewrite_messages(
                question=question,
                history=history,
                max_queries=settings.rag_rewrite_query_count,
            )
        )
        return {"queries": _dedupe_queries(question, _parse_rewrite_queries(result))}
    except Exception:
        logger.exception(
            "问题改写失败，使用原始问题检索，session_id=%s, user_id=%s, question=%s",
            state.get("session_id"),
            state.get("user_id"),
            question,
        )
        return {"queries": [question]}


async def multi_retrieve(state: RagState) -> dict[str, Any]:
    if state.get("error") or state.get("intent") == "general_chat":
        return {"candidates": []}

    user_id = state.get("user_id")
    candidates: list[dict] = []
    try:
        for query in state.get("queries", []) or [state.get("question", "")]:
            results = await search_chunks(query, user_id=user_id, limit=settings.rag_recall_per_query)
            for item in results:
                candidate = dict(item)
                candidate["query"] = query
                candidates.append(candidate)
        return {"candidates": candidates}
    except Exception as exc:
        logger.exception(
            "知识库多路召回失败，session_id=%s, user_id=%s, question=%s",
            state.get("session_id"),
            user_id,
            state.get("question"),
        )
        return {"error": str(exc)}


async def rrf_fusion(state: RagState) -> dict[str, Any]:
    if state.get("error") or state.get("intent") == "general_chat":
        return {"fused_chunks": []}
    return {"fused_chunks": _rrf_fuse(state.get("candidates", []))}


async def rerank_results(state: RagState) -> dict[str, Any]:
    if state.get("error") or state.get("intent") == "general_chat":
        return {"chunks": []}

    question = state.get("question", "")
    business_intent = state.get("business_intent", "other")
    fused_chunks = state.get("fused_chunks", [])
    try:
        chunks = rerank_chunks(question, fused_chunks, top_n=settings.rag_top_k)
        return {"chunks": _filter_relevant_chunks(question, business_intent, chunks)}
    except Exception:
        logger.exception("Rerank 节点失败，使用 RRF 结果。")
        return {"chunks": _filter_relevant_chunks(question, business_intent, fused_chunks)}


async def build_answer_messages(state: RagState) -> dict[str, Any]:
    if state.get("error"):
        return {}

    question = state.get("question", "")
    history = state.get("history", [])
    chunks = state.get("chunks", [])
    intent = state.get("intent", "knowledge_qa")

    if intent == "general_chat":
        messages = build_chat_messages(question=question, history=history)
    elif chunks:
        messages = build_qa_messages(question=question, chunks=chunks, history=history)
    else:
        messages = build_no_knowledge_messages(question=question, history=history)

    return {"messages": messages}


def build_rag_graph():
    graph = StateGraph(RagState)
    graph.add_node("validate_question", validate_question)
    graph.add_node("classify_intent", classify_intent)
    graph.add_node("rewrite_queries", rewrite_queries)
    graph.add_node("multi_retrieve", multi_retrieve)
    graph.add_node("rrf_fusion", rrf_fusion)
    graph.add_node("rerank_results", rerank_results)
    graph.add_node("build_answer_messages", build_answer_messages)
    graph.add_edge(START, "validate_question")
    graph.add_edge("validate_question", "classify_intent")
    graph.add_edge("classify_intent", "rewrite_queries")
    graph.add_edge("rewrite_queries", "multi_retrieve")
    graph.add_edge("multi_retrieve", "rrf_fusion")
    graph.add_edge("rrf_fusion", "rerank_results")
    graph.add_edge("rerank_results", "build_answer_messages")
    graph.add_edge("build_answer_messages", END)
    return graph.compile()


rag_graph = build_rag_graph()


async def rag_answer_stream(payload: dict):
    state = await rag_graph.ainvoke(
        {
            "session_id": payload.get("session_id"),
            "user_id": payload.get("user_id"),
            "question": payload.get("question") or "",
            "history": payload.get("history", []),
            "business_intent": payload.get("business_intent") or "other",
        }
    )

    if state.get("error"):
        content = state["error"] if state["error"].startswith("单次提问") else ANSWER_FAILED_MESSAGE
        yield {
            "event": "message",
            "data": {"type": "delta", "content": content},
        }
        yield {"event": "done", "data": {"sources": []}}
        return

    chunks = state.get("chunks", [])
    async for token in stream_llm(state.get("messages", [])):
        yield {"event": "message", "data": {"type": "delta", "content": token}}

    if chunks:
        yield {
            "event": "source",
            "data": {
                "items": [
                    {
                        "document_id": item.get("document_id"),
                        "chunk_id": item.get("chunk_id"),
                        "doc_name": item["doc_name"],
                        "summary": item["summary"],
                        "score": item["score"],
                    }
                    for item in chunks
                ]
            },
        }
        yield {"event": "done", "data": {"sources_count": len(chunks)}}
    else:
        yield {"event": "done", "data": {"sources": []}}
