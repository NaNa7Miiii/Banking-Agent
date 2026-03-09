"""
Pinecone client and hybrid embeddings (dense + sparse). No dependency on src.
"""
from typing import Any

from refactored.utils.env import load_env, get_env
from refactored.graph.rag_agent.config import (
    DENSE_EMBED_MODEL,
    SPARSE_EMBED_MODEL,
    get_index_name,
)

load_env()

_pc: Any = None


def get_pinecone():
    global _pc
    if _pc is None:
        key = get_env("PINECONE_API_KEY")
        if not key:
            raise RuntimeError("PINECONE_API_KEY is required")
        from pinecone import Pinecone
        _pc = Pinecone(api_key=key)
    return _pc


def get_index():
    pc = get_pinecone()
    name = get_index_name()
    return pc.Index(name)


def _as_list(obj, key: str, default=None):
    if obj is None:
        return default or []
    if hasattr(obj, key):
        return getattr(obj, key, default or [])
    return obj.get(key, default or [])


def _embed_dense(pc, texts: list[str], input_type: str = "passage") -> list[list[float]]:
    if not texts:
        return []
    inputs = [{"text": t} if isinstance(t, str) else t for t in texts]
    out = pc.inference.embed(
        model=DENSE_EMBED_MODEL,
        inputs=inputs,
        parameters={"input_type": input_type, "truncate": "END"},
    )
    data = _as_list(out, "data")
    return [
        item.get("values", getattr(item, "values", []))
        for item in data
    ]


def _embed_sparse(pc, texts: list[str], input_type: str = "passage") -> list[dict]:
    if not texts:
        return []
    inputs = [{"text": t} if isinstance(t, str) else t for t in texts]
    out = pc.inference.embed(
        model=SPARSE_EMBED_MODEL,
        inputs=inputs,
        parameters={"input_type": input_type, "truncate": "END"},
    )
    data = _as_list(out, "data")
    result = []
    for item in data:
        indices = item.get("sparse_indices", item.get("indices", []))
        values = item.get("sparse_values", item.get("values", []))
        if hasattr(item, "sparse_indices"):
            indices = getattr(item, "sparse_indices", indices)
        if hasattr(item, "sparse_values"):
            values = getattr(item, "sparse_values", values)
        result.append({"indices": indices, "values": values})
    return result


def embed_hybrid_batch(
    pc,
    texts: list[str],
    input_type: str = "passage",
) -> tuple[list[list[float]], list[dict]]:
    """Return (dense_list, sparse_list) for upsert or query."""
    dense = _embed_dense(pc, texts, input_type=input_type)
    sparse = _embed_sparse(pc, texts, input_type=input_type)
    return dense, sparse


def embed_query_hybrid(pc, query: str) -> tuple[list[float], dict]:
    """Single query -> (dense_vector, sparse_vector dict with 'indices' and 'values')."""
    dense_list, sparse_list = embed_hybrid_batch(pc, [query], input_type="query")
    dense = dense_list[0] if dense_list else []
    sp = sparse_list[0] if sparse_list else {"indices": [], "values": []}
    sparse_vector = {"indices": sp.get("indices", []), "values": sp.get("values", [])}
    return dense, sparse_vector
