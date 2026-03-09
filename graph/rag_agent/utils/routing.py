"""
Routing: local confidence threshold -> local_only / web / both / refuse. No dependency on src.
"""
from typing import Literal

from refactored.graph.rag_agent.config import LOCAL_CONFIDENCE_THRESHOLD
from refactored.graph.rag_agent.utils.retrieval import retrieve_with_rerank


RouteDecision = Literal["local_only", "web", "both", "refuse"]


def compute_local_confidence(chunks: list[dict]) -> float:
    if not chunks:
        return 0.0
    scores = [c.get("score") for c in chunks if c.get("score") is not None]
    if not scores:
        return 0.0
    return float(max(scores))


def route(
    question: str,
    namespace: str,
    filter_dict: dict | None = None,
    confidence_threshold: float | None = None,
    vector_top_k: int = 40,
    rerank_top_n: int = 5,
) -> tuple[RouteDecision, list[dict], float]:
    chunks = retrieve_with_rerank(
        question, namespace,
        vector_top_k=vector_top_k,
        rerank_top_n=rerank_top_n,
        filter_dict=filter_dict,
    )
    conf = compute_local_confidence(chunks)
    threshold = confidence_threshold if confidence_threshold is not None else LOCAL_CONFIDENCE_THRESHOLD
    if not chunks:
        return "web", [], 0.0
    if conf >= threshold:
        return "local_only", chunks, conf
    return "both", chunks, conf
