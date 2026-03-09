"""
CLI to upsert PDFs from a folder (e.g. CIBC_docs) to Pinecone hybrid index.
Usage (from project root):
  python -m src.ingest.run_upsert [folder_path] [namespace]
"""
import sys
from pathlib import Path

_root = Path(__file__).resolve().parent.parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from src.utils.env import load_env
from src.ingest import process_folder
from src.graph.rag_agent.config import get_default_namespace

load_env()


def main():
    default_folder = _root / "resources" / "CIBC_docs"
    folder = sys.argv[1] if len(sys.argv) > 1 else str(default_folder)
    namespace = sys.argv[2] if len(sys.argv) > 2 else get_default_namespace()
    print(f"Upserting PDFs from: {folder}")
    print(f"Namespace: {namespace}")
    success, total_chunks = process_folder(folder, namespace=namespace)
    print(f"Done. Files: {success}, Chunks: {total_chunks}")


if __name__ == "__main__":
    main()
