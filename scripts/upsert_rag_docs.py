"""
Thin wrapper: runs RAG doc upsert via refactored.ingest.
Usage (from project root):  python refactored/scripts/upsert_rag_docs.py [folder] [namespace]
Preferred:  python -m refactored.ingest.run_upsert [folder] [namespace]
"""
import sys
from pathlib import Path

root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(root))

from refactored.ingest.run_upsert import main

if __name__ == "__main__":
    main()
