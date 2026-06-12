from sqlalchemy import select

from app.core.database import SessionLocal
from app.models.knowledge import KnowledgeChunk, KnowledgeDocument
from app.services.vector_service import upsert_chunks


def main() -> None:
    with SessionLocal() as db:
        rows = db.execute(
            select(KnowledgeChunk, KnowledgeDocument)
            .join(KnowledgeDocument, KnowledgeDocument.id == KnowledgeChunk.document_id)
            .where(KnowledgeDocument.status == "就绪")
            .order_by(KnowledgeChunk.id)
        ).all()

    chunks = [
        {
            "id": chunk.id,
            "user_id": document.user_id,
            "document_id": document.id,
            "doc_name": document.name,
            "content": chunk.content,
            "summary": chunk.summary,
        }
        for chunk, document in rows
    ]
    upsert_chunks(chunks)
    print(f"已重建 {len(chunks)} 个知识片段的 Qdrant 向量索引。")


if __name__ == "__main__":
    main()
