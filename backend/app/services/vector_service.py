from qdrant_client import QdrantClient
from qdrant_client.http.exceptions import UnexpectedResponse
from qdrant_client.http import models

from app.core.config import settings
from app.services.embedding_service import embed_text, embed_texts
from app.services.sparse_service import build_sparse_vector

DENSE_VECTOR_NAME = "dense"
SPARSE_VECTOR_NAME = "sparse"
PAYLOAD_INDEX_FIELDS = ("document_id",)


def get_qdrant_client() -> QdrantClient:
    """
    获取 Qdrant 客户端。

    :return: QdrantClient 实例。
    """
    return QdrantClient(
        url=settings.qdrant_url,
        api_key=settings.qdrant_api_key or None,
    )


def _collection_exists(client: QdrantClient) -> bool:
    """
    判断配置的 Qdrant collection 是否存在。

    :param client: Qdrant 客户端。
    :return: collection 存在时返回 True。
    """
    collection_name = settings.qdrant_collection
    collections = client.get_collections().collections
    return any(collection.name == collection_name for collection in collections)


def _ensure_payload_indexes(client: QdrantClient) -> None:
    """
    确保 Qdrant payload 过滤字段已创建索引。

    :param client: Qdrant 客户端。
    :return: None。
    """
    collection_name = settings.qdrant_collection
    for field_name in PAYLOAD_INDEX_FIELDS:
        try:
            # document_id 会作为删除过滤条件，云端 Qdrant 需要显式 payload index。
            client.create_payload_index(
                collection_name=collection_name,
                field_name=field_name,
                field_schema=models.PayloadSchemaType.INTEGER,
                wait=True,
            )
        except UnexpectedResponse as exc:
            message = str(exc)
            if "already exists" not in message and "already" not in message.lower():
                raise


def _ensure_collection(client: QdrantClient, vector_size: int) -> None:
    """
    确保 Qdrant collection 存在且支持当前混合检索配置。

    :param client: Qdrant 客户端。
    :param vector_size: dense 向量维度。
    :return: None。
    """
    collection_name = settings.qdrant_collection
    if _collection_exists(client):
        # 已存在的 collection 必须同时支持 dense 和 sparse，且 dense 维度与当前 embedding 一致。
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
        _ensure_payload_indexes(client)
        return

    # 首次写入时按当前 embedding 维度自动创建支持 hybrid 检索的 collection。
    client.create_collection(
        collection_name=collection_name,
        vectors_config={
            DENSE_VECTOR_NAME: models.VectorParams(size=vector_size, distance=models.Distance.COSINE),
        },
        sparse_vectors_config={
            SPARSE_VECTOR_NAME: models.SparseVectorParams(),
        },
    )
    _ensure_payload_indexes(client)


def upsert_chunks(chunks: list[dict]) -> None:
    """
    将知识库切片写入 Qdrant 向量库。

    :param chunks: 知识库切片字典列表。
    :return: None。
    """
    texts = [item["content"] for item in chunks]
    dense_vectors = embed_texts(texts)
    if not dense_vectors:
        return

    client = get_qdrant_client()
    _ensure_collection(client, len(dense_vectors[0]))
    # 同一个 point 同时写 dense 向量和 sparse 向量，后续可做语义+关键词混合召回。
    points = [
        models.PointStruct(
            id=item["id"],
            vector={
                DENSE_VECTOR_NAME: dense_vector,
                SPARSE_VECTOR_NAME: build_sparse_vector(item["content"]),
            },
            payload={
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


async def search_chunks(question: str, limit: int | None = None):
    """
    使用 dense + sparse hybrid 检索知识库切片。

    :param question: 用户问题。
    :param limit: 最大返回数量。
    :return: 命中的知识片段列表。
    """
    dense_vector = embed_text(question)
    sparse_vector = build_sparse_vector(question)
    client = get_qdrant_client()
    _ensure_collection(client, len(dense_vector))

    search_limit = limit or settings.rag_top_k
    # Qdrant 原生 hybrid：dense/sparse 各自 prefetch，再用 RRF 融合成最终排序。
    response = client.query_points(
        collection_name=settings.qdrant_collection,
        prefetch=[
            models.Prefetch(
                query=dense_vector,
                using=DENSE_VECTOR_NAME,
                limit=search_limit * 2,
            ),
            models.Prefetch(
                query=sparse_vector,
                using=SPARSE_VECTOR_NAME,
                limit=search_limit * 2,
            ),
        ],
        query=models.FusionQuery(fusion=models.Fusion.RRF),
        limit=search_limit,
        with_payload=True,
    )

    chunks = []
    for rank, item in enumerate(response.points, start=1):
        payload = item.payload or {}
        chunks.append(
            {
                "document_id": payload.get("document_id"),
                "chunk_id": payload.get("chunk_id"),
                "doc_name": payload.get("doc_name", "未知文档"),
                "summary": payload.get("summary") or payload.get("content", "")[:120],
                "content": payload.get("content", ""),
                "score": round(item.score, 4),
                "rank": rank,
            }
        )
    return chunks


def delete_document_vectors(document_id: int) -> None:
    """
    删除指定文档在 Qdrant 中的向量数据。

    :param document_id: 文档 ID。
    :return: None。
    """
    client = get_qdrant_client()
    if not _collection_exists(client):
        return

    # 企业知识库按 document_id 删除对应向量。
    must = [
        models.FieldCondition(
            key="document_id",
            match=models.MatchValue(value=document_id),
        )
    ]

    client.delete(
        collection_name=settings.qdrant_collection,
        points_selector=models.FilterSelector(filter=models.Filter(must=must)),
    )
