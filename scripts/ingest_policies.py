"""Ingestion script for policy documents. Run: python -m scripts.ingest_policies"""
from __future__ import annotations

import sys

from app.rag.pipeline import ingest_documents


def main():
    docs_dir = sys.argv[1] if len(sys.argv) > 1 else "documents/policies"
    count = ingest_documents(docs_dir)
    print(f"Ingested {count} chunks from {docs_dir}")


if __name__ == "__main__":
    main()
