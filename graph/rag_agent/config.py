"""
RAG agent config. Index name, namespace, models, chunk settings. No dependency on src.
"""
from refactored.utils.env import load_env, get_env

load_env()

# Pinecone hybrid index: dense (llama-text-embed-v2, 1024 dim) + sparse (pinecone-sparse-english-v0)
DEFAULT_INDEX_NAME = "cibc-docs-hybrid"
DEFAULT_NAMESPACE = "cibc-en"
DENSE_EMBED_MODEL = "llama-text-embed-v2"
SPARSE_EMBED_MODEL = "pinecone-sparse-english-v0"
DENSE_DIMENSION = 1024
RERANK_MODEL = "bge-reranker-v2-m3"

CHUNK_SIZE = 1000
CHUNK_OVERLAP = 200

# Routing: local confidence above this -> no web fallback
LOCAL_CONFIDENCE_THRESHOLD = 0.5


def get_index_name() -> str:
    return get_env("PINECONE_INDEX_NAME") or DEFAULT_INDEX_NAME


def get_default_namespace() -> str:
    return get_env("RAG_DEFAULT_NAMESPACE") or DEFAULT_NAMESPACE
