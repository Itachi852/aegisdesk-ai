import hashlib
import math
import re
from collections import Counter

from qdrant_client.http import models


SPARSE_VECTOR_SIZE = 2**31 - 1


def _tokens(text: str) -> list[str]:
    words = re.findall(r"[A-Za-z0-9_]+", text.lower())
    chinese_chars = re.findall(r"[一-鿿]", text)
    chinese_bigrams = [text[index : index + 2] for index in range(max(len(text) - 1, 0))]
    chinese_bigrams = [token for token in chinese_bigrams if re.fullmatch(r"[一-鿿]{2}", token)]
    return words + chinese_chars + chinese_bigrams


def _token_index(token: str) -> int:
    digest = hashlib.md5(token.encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % SPARSE_VECTOR_SIZE


def build_sparse_vector(text: str) -> models.SparseVector:
    counts = Counter(_tokens(text))
    if not counts:
        return models.SparseVector(indices=[], values=[])

    weighted: dict[int, float] = {}
    for token, count in counts.items():
        index = _token_index(token)
        weighted[index] = weighted.get(index, 0.0) + 1.0 + math.log(count)

    indices = sorted(weighted)
    values = [weighted[index] for index in indices]
    return models.SparseVector(indices=indices, values=values)
