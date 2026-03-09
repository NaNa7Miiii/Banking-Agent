"""
PDF load and split for RAG ingest. No dependency on src or langchain.
"""
import re
from pathlib import Path

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None


def list_pdf_files(folder_path: str) -> list[str]:
    folder = Path(folder_path)
    if not folder.is_dir():
        return []
    return [
        str(p) for p in folder.iterdir()
        if p.is_file() and p.suffix.lower() == ".pdf"
    ]


def extract_text_from_pdf(pdf_path: str) -> str:
    if fitz is None:
        raise RuntimeError("PyMuPDF (fitz) is required for PDF extraction. pip install pymupdf")
    doc = fitz.open(pdf_path)
    try:
        return "".join(page.get_text() for page in doc)
    finally:
        doc.close()


def split_text(
    text: str,
    chunk_size: int = 1000,
    chunk_overlap: int = 200,
) -> list[str]:
    """Split by paragraphs then by size with overlap; no langchain dependency."""
    if not text or chunk_size <= 0:
        return []
    parts = re.split(r"\n\s*\n", text)
    chunks = []
    current = []
    current_len = 0
    for p in parts:
        p = p.strip()
        if not p:
            continue
        if current_len + len(p) + 1 <= chunk_size:
            current.append(p)
            current_len += len(p) + 1
        else:
            if current:
                chunk = "\n\n".join(current)
                chunks.append(chunk)
            overlap_len = 0
            overlap = []
            for x in reversed(current):
                if overlap_len + len(x) + 1 <= chunk_overlap:
                    overlap.insert(0, x)
                    overlap_len += len(x) + 1
                else:
                    break
            if len(p) <= chunk_size:
                current = overlap + [p]
                current_len = overlap_len + len(p) + 1
            else:
                for i in range(0, len(p), chunk_size - chunk_overlap):
                    piece = p[i : i + chunk_size]
                    if piece:
                        chunks.append(piece)
                current = []
                current_len = 0
    if current:
        chunks.append("\n\n".join(current))
    return chunks
