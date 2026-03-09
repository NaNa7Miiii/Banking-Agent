"""
Upsert PDFs to Pinecone hybrid index. Ingest-only; not part of agent runtime utils.
"""
import re
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from refactored.graph.rag_agent.config import (
    DENSE_DIMENSION,
    CHUNK_SIZE,
    CHUNK_OVERLAP,
    get_default_namespace,
    get_index_name,
)
from refactored.graph.rag_agent.utils.embedding import get_pinecone, embed_hybrid_batch
from refactored.ingest.rag.pdf import list_pdf_files, extract_text_from_pdf, split_text

# Replace common Unicode punctuation with ASCII so Pinecone request body is Latin-1 safe
_UNICODE_REPLACES = [
    ("\u201c", '"'), ("\u201d", '"'), ("\u2018", "'"), ("\u2019", "'"),
    ("\u2013", "-"), ("\u2014", "-"), ("\u2022", "-"), ("\u00a0", " "),
]


def _sanitize_metadata_text(text: str, max_len: int = 50_000) -> str:
    if not text:
        return ""
    s = text[:max_len]
    for a, b in _UNICODE_REPLACES:
        s = s.replace(a, b)
    return s.encode("ascii", errors="replace").decode("ascii")


def _infer_doc_type(filename: str) -> str:
    name = Path(filename).stem.lower()
    if "agreement" in name or "service" in name:
        return "agreement"
    if "policy" in name or "privacy" in name:
        return "policy"
    if "deposit" in name:
        return "deposits"
    if "certificate" in name or "cert" in name:
        return "certificate"
    if "disclosure" in name:
        return "disclosure"
    return "other"


def _infer_language(filename: str) -> str:
    if "-en" in filename.lower() or "_en" in filename.lower():
        return "en"
    if "-fr" in filename.lower() or "_fr" in filename.lower():
        return "fr"
    return "en"


def ensure_hybrid_index(pc, index_name: str) -> None:
    from pinecone import ServerlessSpec
    existing = pc.list_indexes().names()
    if index_name in existing:
        return
    pc.create_index(
        name=index_name,
        dimension=DENSE_DIMENSION,
        metric="dotproduct",
        spec=ServerlessSpec(cloud="aws", region="us-east-1"),
    )


def process_document(
    pdf_path: str,
    index,
    pc,
    namespace: str,
    chunk_size: int = CHUNK_SIZE,
    chunk_overlap: int = CHUNK_OVERLAP,
    language: str | None = None,
    doc_type: str | None = None,
    batch_size: int = 32,
) -> int:
    text = extract_text_from_pdf(pdf_path)
    chunks = split_text(text, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    if not chunks:
        return 0

    source = Path(pdf_path).name
    lang = language or _infer_language(pdf_path)
    dtype = doc_type or _infer_doc_type(pdf_path)

    total_upserted = 0
    for start in range(0, len(chunks), batch_size):
        raw_batch = chunks[start:start + batch_size]
        batch = [_sanitize_metadata_text(c) for c in raw_batch]
        dense_list, sparse_list = embed_hybrid_batch(pc, batch, input_type="passage")
        vectors = []
        for i, (chunk, dense, sparse) in enumerate(zip(batch, dense_list, sparse_list)):
            vec_id = str(uuid.uuid4())
            metadata = {
                "text": chunk,
                "chunk_index": start + i,
                "source": source,
                "language": lang,
                "doc_type": dtype,
            }
            record = {
                "id": vec_id,
                "values": dense,
                "metadata": metadata,
            }
            if sparse and (sparse.get("indices") or sparse.get("values")):
                record["sparse_values"] = {
                    "indices": sparse.get("indices", []),
                    "values": sparse.get("values", []),
                }
            vectors.append(record)
        index.upsert(vectors=vectors, namespace=namespace)
        total_upserted += len(vectors)
    return total_upserted


def process_folder(
    folder_path: str,
    namespace: str | None = None,
    index_name: str | None = None,
    max_workers: int = 4,
) -> tuple[int, int]:
    pc = get_pinecone()
    name = index_name or get_index_name()
    ensure_hybrid_index(pc, name)
    index = pc.Index(name)
    ns = namespace or get_default_namespace()

    pdfs = list_pdf_files(folder_path)
    if not pdfs:
        return 0, 0

    success, total = 0, len(pdfs)
    total_chunks = 0
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {
            ex.submit(process_document, path, index, pc, ns): path
            for path in pdfs
        }
        for fut in as_completed(futures):
            path = futures[fut]
            try:
                n = fut.result()
                total_chunks += n
                success += 1
            except Exception as e:
                print(f"Failed {path}: {e}")
    return success, total_chunks
