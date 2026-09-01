import json
import logging
from pathlib import Path

import faiss
import numpy as np

logger = logging.getLogger("banking_assistant")

THRESHOLD = 0.70
INDEX_DIR = Path(__file__).resolve().parent / "index"

# Sentence-level chunking is precise for narrow factual questions ("what is
# the minimum balance") but under-scores broader phrasing like "what is the
# card blocking policy?", where no single sentence alone is a strong match.
# When several of the retrieved chunks agree on the same source document,
# that agreement is real corroborating evidence, so it earns a small,
# capped confidence boost. The cap keeps this from ever manufacturing
# confidence out of nothing — an irrelevant question's chunks score near
# zero individually, and near zero plus the small cap is still nowhere
# near the threshold.
RETRIEVE_TOP_K = 4
AGREEMENT_BOOST_PER_CHUNK = 0.04
AGREEMENT_BOOST_CAP = 0.15

_model = None
_index = None
_chunks = None


def _load():
    global _model, _index, _chunks
    if _index is not None:
        return
    index_path = INDEX_DIR / "index.faiss"
    chunks_path = INDEX_DIR / "chunks.json"
    if not index_path.exists() or not chunks_path.exists():
        raise FileNotFoundError("RAG index not found. Run 'python -m rag.ingest' first.")
    from sentence_transformers import SentenceTransformer
    _model = SentenceTransformer("all-MiniLM-L6-v2")
    _index = faiss.read_index(str(index_path))
    _chunks = json.loads(chunks_path.read_text(encoding="utf-8"))


def retrieve(question: str, top_k: int = 2):
    _load()
    query = _model.encode([question], normalize_embeddings=True)
    scores, indices = _index.search(np.asarray(query, dtype="float32"), top_k)
    results = []
    for score, idx in zip(scores[0], indices[0]):
        if idx == -1:
            continue
        chunk = _chunks[idx]
        results.append({"score": float(score), "text": chunk["text"], "source": chunk["source"]})
    return results


SAFE_FALLBACK_ANSWER = "I'm having trouble accessing the banking policy information right now. Please try again."


def answer_policy(question: str):
    try:
        results = retrieve(question, top_k=RETRIEVE_TOP_K)
    except FileNotFoundError:
        logger.error("RAG index not built — run 'python -m rag.ingest'")
        return {"answer": "Policy lookup is unavailable right now — the knowledge base index hasn't been built yet.", "route": "Fallback", "confidence": 0.0, "source": None}
    except Exception:
        # Any other failure (missing embedding library, corrupted index,
        # FAISS load error, etc.) must never surface as a raw 500 — log
        # the real cause for developers and answer with a safe fallback.
        logger.exception("RAG retrieval failed for question: %r", question)
        return {"answer": SAFE_FALLBACK_ANSWER, "route": "Fallback", "confidence": 0.0, "source": None}

    if not results:
        return {"answer": "I couldn't find enough information in the current banking policy documents to answer that confidently.", "route": "Fallback", "confidence": 0.0, "source": None}

    top = results[0]
    corroborating = [r for r in results if r["source"] == top["source"]]
    agreement_boost = min(AGREEMENT_BOOST_CAP, AGREEMENT_BOOST_PER_CHUNK * (len(corroborating) - 1))
    confidence = min(1.0, top["score"] + agreement_boost)

    if confidence < THRESHOLD:
        return {"answer": "I couldn't find enough information in the current banking policy documents to answer that confidently.", "route": "Fallback", "confidence": confidence, "source": None}

    other_source = next((r for r in results if r["source"] != top["source"]), None)
    conflict = other_source is not None and (top["score"] - other_source["score"]) < 0.05
    if conflict:
        return {
            "answer": "I found conflicting policy information for this question across our documents. Please confirm with a bank representative to be sure.",
            "route": "Escalation",
            "confidence": confidence,
            "source": top["source"],
            "conflict": True,
        }

    context = " ".join(r["text"] for r in corroborating[:3])
    from llm.groq_client import generate_rag_answer
    answer = generate_rag_answer(question, context, top["source"])
    return {"answer": answer, "route": "RAG Agent", "confidence": confidence, "source": top["source"]}
