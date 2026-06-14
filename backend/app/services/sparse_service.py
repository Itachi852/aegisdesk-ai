import hashlib
import math
import re
from collections import Counter

from qdrant_client.http import models


SPARSE_VECTOR_SIZE = 2**31 - 1


def _tokens(text: str) -> list[str]:
    """
    将文本拆成用于关键词召回的 token。

    :param text: 原始文本。
    :return: token 列表。
    """
    # 简单关键词召回：英文按词切分，中文同时保留单字和二元片段。
    words = re.findall(r"[A-Za-z0-9_]+", text.lower())
    chinese_chars = re.findall(r"[一-鿿]", text)
    chinese_bigrams = [text[index : index + 2] for index in range(max(len(text) - 1, 0))]
    chinese_bigrams = [token for token in chinese_bigrams if re.fullmatch(r"[一-鿿]{2}", token)]
    return words + chinese_chars + chinese_bigrams


def _token_index(token: str) -> int:
    """
    将 token 映射为稀疏向量索引。

    :param token: 文本 token。
    :return: 稀疏向量索引。
    """
    # 用稳定 hash 把 token 映射到稀疏向量维度，避免维护词表。
    digest = hashlib.md5(token.encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % SPARSE_VECTOR_SIZE


def build_sparse_vector(text: str) -> models.SparseVector:
    """
    根据文本构建 Qdrant 稀疏向量。

    :param text: 原始文本。
    :return: Qdrant SparseVector 对象。
    """
    counts = Counter(_tokens(text))
    if not counts:
        return models.SparseVector(indices=[], values=[])

    weighted: dict[int, float] = {}
    for token, count in counts.items():
        # 高频词略微增权，但用 log 控制权重增长，避免长文档中的重复词压倒其他词。
        index = _token_index(token)
        weighted[index] = weighted.get(index, 0.0) + 1.0 + math.log(count)

    indices = sorted(weighted)
    values = [weighted[index] for index in indices]
    return models.SparseVector(indices=indices, values=values)
