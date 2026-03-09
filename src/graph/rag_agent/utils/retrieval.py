"""
Hybrid retrieval (dense + sparse) and rerank. No dependency on src.
"""
from typing import Any

from src.graph.rag_agent.config import RERANK_MODEL
from src.graph.rag_agent.utils.embedding import get_pinecone, get_index, embed_query_hybrid


def hybrid_query(
    index,
    pc,
    query: str,
    namespace: str,
    top_k: int = 40,
    filter_dict: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    dense, sparse_vector = embed_query_hybrid(pc, query)
    kwargs = {
        "vector": dense,
        "top_k": top_k,
        "namespace": namespace,
        "include_metadata": True,
    }
    if sparse_vector and (sparse_vector.get("indices") or sparse_vector.get("values")):
        kwargs["sparse_vector"] = sparse_vector
    if filter_dict:
        kwargs["filter"] = filter_dict
    response = index.query(**kwargs)
    matches = response.get("matches", [])
    return [
        {
            "id": m.get("id"),
            "text": (m.get("metadata") or {}).get("text", ""),
            "source": (m.get("metadata") or {}).get("source", ""),
            "score": m.get("score"),
        }
        for m in matches if (m.get("metadata") or {}).get("text")
    ]


def rerank(
    pc,
    query: str,
    documents: list[dict],
    top_n: int = 5,
    text_field: str = "text",
) -> list[dict]:
    if not documents:
        return []
    result = pc.inference.rerank(
        model=RERANK_MODEL,
        query=query,
        documents=documents,
        top_n=top_n,
        rank_fields=[text_field],
        return_documents=True,
        parameters={"truncate": "END"},
    )
    data = result.get("data", result.get("results", []))
    out = []
    for row in data:
        if isinstance(row, dict):
            doc = row.get("document", row)
            score = row.get("score")
        else:
            doc = getattr(row, "document", row)
            score = getattr(row, "score", None)
        text = doc.get("text", doc) if isinstance(doc, dict) else getattr(doc, "text", str(doc))
        out.append({
            "id": doc.get("id") if isinstance(doc, dict) else getattr(doc, "id", None),
            "source": doc.get("source") if isinstance(doc, dict) else getattr(doc, "source", ""),
            "text": text,
            "score": score,
        })
    return out


def retrieve_with_rerank(
    query: str,
    namespace: str,
    vector_top_k: int = 40,
    rerank_top_n: int = 5,
    filter_dict: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    pc = get_pinecone()
    index = get_index()
    candidates = hybrid_query(
        index, pc, query, namespace,
        top_k=vector_top_k,
        filter_dict=filter_dict,
    )
    if not candidates:
        return []
    reranked = rerank(pc, query, candidates, top_n=rerank_top_n, text_field="text")
    return reranked
