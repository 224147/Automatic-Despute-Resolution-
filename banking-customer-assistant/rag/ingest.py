"""Builds the FAISS index from knowledge_base/*.md.

Run once (and again whenever the knowledge base changes):
    python -m rag.ingest
"""
import json
import re
from pathlib import Path

import faiss
import numpy as np
from sentence_transformers import SentenceTransformer

KB_DIR = Path(__file__).resolve().parent.parent / "knowledge_base"
INDEX_DIR = Path(__file__).resolve().parent / "index"
MODEL_NAME = "all-MiniLM-L6-v2"

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


def load_chunks():
    """Sentence-level chunks retrieve more precisely than whole paragraphs
    for short, direct factual questions typical of a banking FAQ."""
    chunks = []
    for path in sorted(KB_DIR.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        for paragraph in text.split("\n\n"):
            paragraph = paragraph.strip()
            if not paragraph or paragraph.startswith("# "):
                continue
            for sentence in _SENTENCE_SPLIT.split(paragraph):
                sentence = sentence.strip()
                if sentence:
                    chunks.append({"text": sentence, "source": path.name})
    return chunks


def build_index():
    chunks = load_chunks()
    if not chunks:
        raise RuntimeError(f"No knowledge base documents found in {KB_DIR}")

    model = SentenceTransformer(MODEL_NAME)
    embeddings = model.encode([c["text"] for c in chunks], normalize_embeddings=True)

    index = faiss.IndexFlatIP(embeddings.shape[1])
    index.add(np.asarray(embeddings, dtype="float32"))

    INDEX_DIR.mkdir(exist_ok=True)
    faiss.write_index(index, str(INDEX_DIR / "index.faiss"))
    (INDEX_DIR / "chunks.json").write_text(json.dumps(chunks, indent=2), encoding="utf-8")
    print(f"Indexed {len(chunks)} chunks from {KB_DIR} into {INDEX_DIR}")


if __name__ == "__main__":
    build_index()
