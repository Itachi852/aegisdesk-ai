from app.core.config import settings


async def search_chunks(question: str):
    # TODO: embed question and search Qdrant with score threshold.
    return [
        {
            "doc_name": "常见问题FAQ.md",
            "summary": "示例知识片段，用于验证 RAG 流式链路。",
            "content": "这里是检索到的知识内容。",
            "score": settings.rag_score_threshold + 0.1,
        }
    ]
