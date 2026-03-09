"""Ingest tools (e.g. RAG doc upsert). Not part of agent runtime; for admin/ops."""
from src.ingest.rag import process_folder, process_document

__all__ = ["process_folder", "process_document"]
