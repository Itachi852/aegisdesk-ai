from sqlalchemy import select

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.knowledge import KnowledgeChunk, KnowledgeDocument


def expand_adjacent_chunks(chunks: list[dict]) -> list[dict]:
    """
    根据命中的 chunk 补充同文档前后相邻 chunk。

    :param chunks: RAG 已命中的知识片段。
    :return: 补充相邻片段后的知识片段列表。
    """
    window = settings.rag_adjacent_chunk_window
    if window <= 0 or not chunks:
        return chunks

    expanded: dict[int, dict] = {}
    with SessionLocal() as db:
        for item in chunks:
            document_id = item.get("document_id")
            chunk_id = item.get("chunk_id")
            if not document_id or not chunk_id:
                continue

            lower_id = max(int(chunk_id) - window, 1)
            upper_id = int(chunk_id) + window
            rows = db.execute(
                select(KnowledgeChunk, KnowledgeDocument.name)
                .join(KnowledgeDocument, KnowledgeDocument.id == KnowledgeChunk.document_id)
                .where(
                    KnowledgeChunk.document_id == document_id,
                    KnowledgeChunk.id >= lower_id,
                    KnowledgeChunk.id <= upper_id,
                )
                .order_by(KnowledgeChunk.id)
            ).all()

            for chunk, doc_name in rows:
                expanded[chunk.id] = {
                    "document_id": chunk.document_id,
                    "chunk_id": chunk.id,
                    "doc_name": doc_name,
                    "summary": chunk.summary or chunk.content[:120],
                    "content": chunk.content,
                    "score": item.get("score"),
                    "rerank_score": item.get("rerank_score"),
                    "expanded_from_chunk_id": chunk_id,
                }

    if not expanded:
        return chunks

    return sorted(expanded.values(), key=lambda value: (value["document_id"], value["chunk_id"]))
