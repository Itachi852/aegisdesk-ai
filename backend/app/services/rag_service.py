from app.core.config import settings
from app.prompts.qa_prompt import build_general_prompt, build_qa_prompt
from app.services.llm_service import stream_llm
from app.services.vector_service import search_chunks


async def rag_answer_stream(payload: dict):
    question = (payload.get("question") or "").strip()
    user_id = payload.get("user_id")
    if len(question) > settings.max_question_length:
        yield {"event": "error", "data": {"message": "单次提问不能超过 500 字"}}
        return

    chunks = await search_chunks(question, user_id=user_id)
    if not chunks:
        prompt = build_general_prompt(question=question, history=payload.get("history", []))
        async for token in stream_llm(prompt):
            yield {"event": "message", "data": {"type": "delta", "content": token}}

        yield {"event": "done", "data": {"sources": []}}
        return

    prompt = build_qa_prompt(question=question, chunks=chunks, history=payload.get("history", []))
    async for token in stream_llm(prompt):
        yield {"event": "message", "data": {"type": "delta", "content": token}}

    yield {
        "event": "source",
        "data": {
            "items": [
                {"doc_name": item["doc_name"], "summary": item["summary"], "score": item["score"]}
                for item in chunks
            ]
        },
    }
    yield {"event": "done", "data": {"sources_count": len(chunks)}}
