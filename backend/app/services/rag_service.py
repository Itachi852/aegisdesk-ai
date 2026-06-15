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
from app.services.chunk_context_service import expand_adjacent_chunks
from app.services.intent_service import get_business_intent_keywords
from app.services.llm_service import invoke_llm_text, stream_llm
from app.services.rerank_service import rerank_chunks
from app.services.vector_service import search_chunks

ANSWER_FAILED_MESSAGE = "抱歉，当前暂时无法生成回答，请稍后再试。"
Intent = Literal["knowledge_qa", "general_chat"]
logger = logging.getLogger(__name__)


class RagState(TypedDict, total=False):
    # LangGraph 节点之间共享的状态；每个节点只补充自己负责的字段。
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
    """
    合并原问题和改写问题，并去除重复 query。

    :param question: 用户原始问题。
    :param rewritten_queries: LLM 生成的改写问题列表。
    :return: 去重后的检索 query 列表。
    """
    # 原问题必须保留在第一位，改写问题只作为额外召回入口。
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
    """
    生成候选片段去重用的稳定 key。

    :param item: 候选知识片段。
    :return: 候选片段 key。
    """
    return str(item.get("chunk_id") or f"{item.get('document_id')}:{item.get('content', '')[:80]}")


def _parse_rewrite_queries(text: str) -> list[str]:
    """
    解析 LLM 返回的问题改写 JSON 数组。

    :param text: LLM 原始输出。
    :return: 改写后的 query 列表。
    """
    # LLM 可能返回 ```json 包裹内容，这里抽取出 JSON 数组再解析。
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
    """
    对多个 query 的召回结果执行 RRF 融合。

    :param candidates: 多路召回候选片段。
    :return: 融合排序后的片段列表。
    """
    # 外层 RRF 用于融合多个改写 query 的召回结果，避免只相信某一次检索排序。
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


def _truncate_log_text(value: Any, max_length: int = 120) -> str:
    """
    截断日志中的长文本字段，避免调试日志过大。

    :param value: 原始字段值。
    :param max_length: 最大保留长度。
    :return: 适合写入日志的短文本。
    """
    text = str(value or "").replace("\r", " ").replace("\n", " ").strip()
    if len(text) <= max_length:
        return text
    return f"{text[:max_length]}..."


def _log_rag_chunks(stage: str, state: RagState, chunks: list[dict]) -> None:
    """
    打印 RAG 某个阶段的候选 chunk 排名和分数。

    :param stage: RAG 阶段名。
    :param state: LangGraph 当前状态。
    :param chunks: 当前阶段的 chunk 列表。
    :return: None。
    """
    if not settings.rag_debug_log_enabled:
        return

    top_n = max(int(settings.rag_debug_log_top_n or 0), 0)
    if top_n <= 0:
        return

    limited_chunks = chunks[:top_n]
    logger.info(
        "RAG调试汇总 stage=%s session_id=%s user_id=%s question=%s total=%s logged=%s",
        stage,
        state.get("session_id"),
        state.get("user_id"),
        _truncate_log_text(state.get("question"), 200),
        len(chunks),
        len(limited_chunks),
    )
    for index, item in enumerate(limited_chunks, start=1):
        logger.info(
            (
                "RAG调试明细 stage=%s rank=%s query=%s document_id=%s chunk_id=%s "
                "doc_name=%s score=%s rerank_score=%s expanded_from_chunk_id=%s "
                "queries=%s query_ranks=%s summary=%s"
            ),
            stage,
            item.get("rank") or index,
            _truncate_log_text(item.get("query"), 120),
            item.get("document_id"),
            item.get("chunk_id"),
            item.get("doc_name"),
            item.get("score"),
            item.get("rerank_score"),
            item.get("expanded_from_chunk_id"),
            item.get("queries"),
            item.get("query_ranks"),
            _truncate_log_text(item.get("summary"), 120),
        )


def _filter_relevant_chunks(question: str, business_intent: str, chunks: list[dict]) -> list[dict]:
    """
    过滤与当前问题弱相关的知识片段。

    :param question: 用户问题。
    :param business_intent: 本地业务意图分类。
    :param chunks: 候选知识片段。
    :return: 过滤后的知识片段列表。
    """
    if not chunks:
        return []

    # 有 Rerank 分数时优先用模型相关性阈值，过滤掉弱相关引用。
    reranked_chunks = [item for item in chunks if item.get("rerank_score") is not None]
    if reranked_chunks:
        high_confidence_chunks = [
            item
            for item in reranked_chunks
            if float(item.get("rerank_score") or 0) >= settings.rag_score_threshold
        ][: settings.rag_top_k]
        if high_confidence_chunks:
            return high_confidence_chunks

    intent_keywords = get_business_intent_keywords(business_intent)
    if not intent_keywords:
        return reranked_chunks[: settings.rag_top_k] if reranked_chunks else chunks[: settings.rag_top_k]

    # Rerank 分数偏低或不可用时，用业务意图关键词做一层保守过滤，减少无关文件被引用。
    fallback_chunks = reranked_chunks or chunks
    relevant_chunks = [
        item
        for item in fallback_chunks
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
    """
    校验用户问题长度并清洗问题文本。

    :param state: LangGraph 当前状态。
    :return: 更新后的状态字段。
    """
    question = (state.get("question") or "").strip()
    if len(question) > settings.max_question_length:
        return {"error": "单次提问不能超过 500 字"}
    return {"question": question}


async def classify_intent(state: RagState) -> dict[str, Any]:
    """
    识别当前问题应走知识库问答还是普通闲聊。

    :param state: LangGraph 当前状态。
    :return: 包含 intent 的状态字段。
    """
    if state.get("error"):
        return {}

    # 这里识别的是 RAG 路由意图：闲聊直接回答，知识问答才进入检索链路。
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
    """
    将用户问题改写为多个适合检索的 query。

    :param state: LangGraph 当前状态。
    :return: 包含 queries 的状态字段。
    """
    if state.get("error") or state.get("intent") == "general_chat":
        return {"queries": []}

    # 对知识问答生成多个检索 query，覆盖同义表达和上下文省略。
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
    """
    对多个 query 执行知识库召回。

    :param state: LangGraph 当前状态。
    :return: 包含 candidates 的状态字段。
    """
    if state.get("error") or state.get("intent") == "general_chat":
        return {"candidates": []}

    # 每个改写 query 都走一次 hybrid 检索，后续再统一融合排序。
    user_id = state.get("user_id")
    candidates: list[dict] = []
    try:
        for query in state.get("queries", []) or [state.get("question", "")]:
            results = await search_chunks(query, limit=settings.rag_recall_per_query)
            query_candidates: list[dict] = []
            for item in results:
                candidate = dict(item)
                candidate["query"] = query
                candidates.append(candidate)
                query_candidates.append(candidate)
            _log_rag_chunks("retrieve", state, query_candidates)
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
    """
    融合多路召回候选片段。

    :param state: LangGraph 当前状态。
    :return: 包含 fused_chunks 的状态字段。
    """
    if state.get("error") or state.get("intent") == "general_chat":
        return {"fused_chunks": []}
    # 第一层 RRF 已在 Qdrant hybrid 内部完成，这里再融合多 query 的召回结果。
    fused_chunks = _rrf_fuse(state.get("candidates", []))
    _log_rag_chunks("rrf", state, fused_chunks)
    return {"fused_chunks": fused_chunks}


async def rerank_results(state: RagState) -> dict[str, Any]:
    """
    对融合后的知识片段执行 Rerank 精排。

    :param state: LangGraph 当前状态。
    :return: 包含 chunks 的状态字段。
    """
    if state.get("error") or state.get("intent") == "general_chat":
        return {"chunks": []}

    question = state.get("question", "")
    business_intent = state.get("business_intent", "other")
    fused_chunks = state.get("fused_chunks", [])
    try:
        # Rerank 是最后一道精排；失败时退回 RRF 结果，保证用户仍能得到回答。
        chunks = rerank_chunks(question, fused_chunks, top_n=settings.rag_top_k)
        _log_rag_chunks("rerank", state, chunks)
        filtered_chunks = _filter_relevant_chunks(question, business_intent, chunks)
        _log_rag_chunks("filtered", state, filtered_chunks)
        expanded_chunks = expand_adjacent_chunks(filtered_chunks)
        _log_rag_chunks("expanded", state, expanded_chunks)
        return {"chunks": expanded_chunks}
    except Exception:
        logger.exception("Rerank 节点失败，使用 RRF 结果。")
        filtered_chunks = _filter_relevant_chunks(question, business_intent, fused_chunks)
        _log_rag_chunks("filtered", state, filtered_chunks)
        expanded_chunks = expand_adjacent_chunks(filtered_chunks)
        _log_rag_chunks("expanded", state, expanded_chunks)
        return {"chunks": expanded_chunks}


async def build_answer_messages(state: RagState) -> dict[str, Any]:
    """
    根据意图和检索结果构建最终回答提示词。

    :param state: LangGraph 当前状态。
    :return: 包含 messages 的状态字段。
    """
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
        # 没有命中知识库也继续让大模型自然回答，而不是直接报错或空回复。
        messages = build_no_knowledge_messages(question=question, history=history)

    return {"messages": messages}


def build_rag_graph():
    """
    构建并编译 RAG LangGraph 工作流。

    :return: 编译后的 LangGraph 应用。
    """
    # RAG 主流程按“校验 -> 路由 -> 改写 -> 召回 -> 融合 -> 重排 -> 组装提示词”串联。
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


def _progress_event(stage: str, message: str) -> dict:
    """
    构造前端展示用的 RAG 进度事件。

    :param stage: 当前处理阶段标识。
    :param message: 前端展示文案。
    :return: SSE 事件结构。
    """
    return {"event": "progress", "data": {"stage": stage, "message": message}}


async def rag_answer_stream(payload: dict):
    """
    执行 RAG 工作流并生成前端 SSE 事件。

    :param payload: 聊天请求上下文。
    :return: SSE 事件异步迭代器。
    """
    # 按节点逐步执行，方便在耗时阶段之间向前端推送可见进度。
    state: RagState = {
        "session_id": payload.get("session_id"),
        "user_id": payload.get("user_id"),
        "question": payload.get("question") or "",
        "history": payload.get("history", []),
        "business_intent": payload.get("business_intent") or "other",
    }

    yield _progress_event("preparing", "正在准备问题...")
    state.update(await validate_question(state))

    yield _progress_event("intent", "正在识别问题类型...")
    state.update(await classify_intent(state))

    if not state.get("error") and state.get("intent") != "general_chat":
        yield _progress_event("rewrite", "正在改写检索问题...")
        state.update(await rewrite_queries(state))

        yield _progress_event("retrieve", "正在检索知识库...")
        state.update(await multi_retrieve(state))
        state.update(await rrf_fusion(state))

        yield _progress_event("rerank", "正在筛选相关资料...")
        state.update(await rerank_results(state))

    yield _progress_event("generate", "正在生成回答...")
    state.update(await build_answer_messages(state))

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
