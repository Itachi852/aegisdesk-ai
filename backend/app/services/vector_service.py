from qdrant_client import QdrantClient
from qdrant_client.http import models

from app.core.config import settings
from app.services.embedding_service import embed_text, embed_texts
from app.services.sparse_service import build_sparse_vector

DENSE_VECTOR_NAME = "dense"
SPARSE_VECTOR_NAME = "sparse"


def get_qdrant_client() -> QdrantClient:
    return QdrantClient(
        url=settings.qdrant_url,
        api_key=settings.qdrant_api_key or None,
    )


def _collection_exists(client: QdrantClient) -> bool:
    collection_name = settings.qdrant_collection
    collections = client.get_collections().collections
    return any(collection.name == collection_name for collection in collections)


def _ensure_collection(client: QdrantClient, vector_size: int) -> None:
    collection_name = settings.qdrant_collection
    if _collection_exists(client):
        collection = client.get_collection(collection_name=collection_name)
        vectors_config = collection.config.params.vectors
        sparse_config = collection.config.params.sparse_vectors or {}

        dense_config = vectors_config.get(DENSE_VECTOR_NAME) if isinstance(vectors_config, dict) else None
        current_size = getattr(dense_config, "size", None)
        if current_size is None:
            raise RuntimeError(
                "当前 Qdrant collection 不是混合检索结构。请新建 collection 或清空旧 collection 后重建索引。"
            )
        if current_size != vector_size:
            raise RuntimeError(
                f"Qdrant dense 向量维度不匹配：当前是 {current_size}，"
                f"新模型输出是 {vector_size}。请新建 collection 或清空旧 collection 后重建索引。"
            )
        if SPARSE_VECTOR_NAME not in sparse_config:
            raise RuntimeError(
                "当前 Qdrant collection 缺少 sparse 向量配置。请新建 collection 或清空旧 collection 后重建索引。"
            )
        return

    client.create_collection(
        collection_name=collection_name,
        vectors_config={
            DENSE_VECTOR_NAME: models.VectorParams(size=vector_size, distance=models.Distance.COSINE),
        },
        sparse_vectors_config={
            SPARSE_VECTOR_NAME: models.SparseVectorParams(),
        },
    )


def _user_filter(user_id: int | None) -> models.Filter | None:
    if user_id is None:
        return None
    return models.Filter(
        must=[
            models.FieldCondition(
                key="user_id",
                match=models.MatchValue(value=user_id),
            )
        ]
    )


def upsert_chunks(chunks: list[dict]) -> None:
    texts = [item["content"] for item in chunks]
    dense_vectors = embed_texts(texts)
    if not dense_vectors:
        return

    client = get_qdrant_client()
    _ensure_collection(client, len(dense_vectors[0]))
    points = [
        models.PointStruct(
            id=item["id"],
            vector={
                DENSE_VECTOR_NAME: dense_vector,
                SPARSE_VECTOR_NAME: build_sparse_vector(item["content"]),
            },
            payload={
                "user_id": item["user_id"],
                "chunk_id": item["id"],
                "document_id": item["document_id"],
                "doc_name": item["doc_name"],
                "content": item["content"],
                "summary": item["summary"],
            },
        )
        for item, dense_vector in zip(chunks, dense_vectors, strict=True)
    ]
    client.upsert(collection_name=settings.qdrant_collection, points=points)


async def search_chunks(question: str, user_id: int | None = None):
    dense_vector = embed_text(question)
    sparse_vector = build_sparse_vector(question)
    client = get_qdrant_client()
    _ensure_collection(client, len(dense_vector))

    query_filter = _user_filter(user_id)
    response = client.query_points(
        collection_name=settings.qdrant_collection,
        prefetch=[
            models.Prefetch(
                query=dense_vector,
                using=DENSE_VECTOR_NAME,
                filter=query_filter,
                limit=settings.rag_top_k * 2,
            ),
            models.Prefetch(
                query=sparse_vector,
                using=SPARSE_VECTOR_NAME,
                filter=query_filter,
                limit=settings.rag_top_k * 2,
            ),
        ],
        query=models.FusionQuery(fusion=models.Fusion.RRF),
        query_filter=query_filter,
        limit=settings.rag_top_k,
        with_payload=True,
    )

    chunks = []
    for item in response.points:
        payload = item.payload or {}
        chunks.append(
            {
                "doc_name": payload.get("doc_name", "未知文档"),
                "summary": payload.get("summary") or payload.get("content", "")[:120],
                "content": payload.get("content", ""),
                "score": round(item.score, 4),
            }
        )
    return chunks


def delete_document_vectors(document_id: int, user_id: int | None = None) -> None:
    client = get_qdrant_client()
    if not _collection_exists(client):
        return

    must = [
        models.FieldCondition(
            key="document_id",
            match=models.MatchValue(value=document_id),
        )
    ]
    if user_id is not None:
        must.append(
            models.FieldCondition(
                key="user_id",
                match=models.MatchValue(value=user_id),
            )
        )

    client.delete(
        collection_name=settings.qdrant_collection,
        points_selector=models.FilterSelector(filter=models.Filter(must=must)),
    )
