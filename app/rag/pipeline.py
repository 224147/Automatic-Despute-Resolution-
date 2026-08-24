"""RAG pipeline for banking policy retrieval."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

import numpy as np

from app.core.config import get_settings
from app.core.logging import get_logger
from app.schemas.schemas import PolicyChunk, RAGResponse

logger = get_logger(__name__)

_vector_store = None
_embeddings = None


class _SimpleHashEmbeddings:
    """Deterministic hash-based embeddings – zero external downloads required.
    Good enough for keyword-overlap retrieval on a small policy corpus."""

    def __init__(self, dim: int = 384):
        self.dim = dim

    def _hash_embed(self, text: str) -> list[float]:
        tokens = text.lower().split()
        vec = np.zeros(self.dim, dtype=np.float32)
        for token in tokens:
            h = int(hashlib.sha256(token.encode()).hexdigest(), 16)
            idx = h % self.dim
            vec[idx] += 1.0
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        return vec.tolist()

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._hash_embed(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._hash_embed(text)


def _get_embeddings():
    global _embeddings
    if _embeddings is None:
        settings = get_settings()
        if settings.embedding_provider == "sentence-transformers":
            try:
                from langchain_community.embeddings import HuggingFaceEmbeddings
                _embeddings = HuggingFaceEmbeddings(model_name=settings.embedding_model)
                logger.info("using_sentence_transformers")
            except Exception as e:
                logger.warning("sentence_transformers_fallback", error=str(e))
                _embeddings = _SimpleHashEmbeddings()
        elif settings.embedding_provider == "simple":
            _embeddings = _SimpleHashEmbeddings()
        else:
            from langchain_openai import OpenAIEmbeddings
            _embeddings = OpenAIEmbeddings(api_key=settings.openai_api_key)
    return _embeddings


def _get_vector_store():
    global _vector_store
    if _vector_store is None:
        settings = get_settings()
        embeddings = _get_embeddings()
        store_path = Path(settings.vector_store_path)
        if store_path.exists() and (store_path / "index.faiss").exists():
            from langchain_community.vectorstores import FAISS
            _vector_store = FAISS.load_local(
                str(store_path), embeddings, allow_dangerous_deserialization=True
            )
            logger.info("vector_store_loaded", path=str(store_path))
        else:
            logger.warning("vector_store_not_found", path=str(store_path))
    return _vector_store


def _load_documents(docs_dir: str) -> list:
    """Load PDF, DOCX, MD, TXT documents from a directory."""
    from langchain_core.documents import Document

    documents = []
    docs_path = Path(docs_dir)
    if not docs_path.exists():
        logger.warning("documents_dir_not_found", path=docs_dir)
        return documents

    for file_path in docs_path.rglob("*"):
        if file_path.suffix.lower() == ".pdf":
            try:
                import fitz  # PyMuPDF

                doc = fitz.open(str(file_path))
                for page_num, page in enumerate(doc):
                    text = page.get_text()
                    if text.strip():
                        documents.append(Document(
                            page_content=text,
                            metadata={
                                "source": file_path.name,
                                "page": page_num + 1,
                                "file_path": str(file_path),
                            },
                        ))
                doc.close()
            except Exception as e:
                logger.error("pdf_load_error", file=str(file_path), error=str(e))

        elif file_path.suffix.lower() in (".md", ".txt"):
            try:
                text = file_path.read_text(encoding="utf-8")
                if text.strip():
                    documents.append(Document(
                        page_content=text,
                        metadata={
                            "source": file_path.name,
                            "page": 1,
                            "file_path": str(file_path),
                        },
                    ))
            except Exception as e:
                logger.error("text_load_error", file=str(file_path), error=str(e))

    logger.info("documents_loaded", count=len(documents))
    return documents


def ingest_documents(docs_dir: str = "documents/policies") -> int:
    """Ingest documents, create chunks, build vector store, persist."""
    global _vector_store

    from langchain_text_splitters import RecursiveCharacterTextSplitter
    from langchain_community.vectorstores import FAISS

    settings = get_settings()
    documents = _load_documents(docs_dir)
    if not documents:
        logger.warning("no_documents_to_ingest")
        return 0

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=settings.rag_chunk_size,
        chunk_overlap=settings.rag_chunk_overlap,
        separators=["\n\n", "\n", ". ", " ", ""],
    )
    chunks = splitter.split_documents(documents)
    logger.info("chunks_created", count=len(chunks))

    embeddings = _get_embeddings()
    _vector_store = FAISS.from_documents(chunks, embeddings)

    store_path = Path(settings.vector_store_path)
    store_path.mkdir(parents=True, exist_ok=True)
    _vector_store.save_local(str(store_path))
    logger.info("vector_store_saved", path=str(store_path), chunks=len(chunks))
    return len(chunks)


async def retrieve_policies(query: str, top_k: int | None = None) -> RAGResponse:
    """Retrieve relevant policy chunks for a dispute query."""
    settings = get_settings()
    k = top_k or settings.rag_top_k
    store = _get_vector_store()

    if store is None:
        logger.warning("no_vector_store_available")
        return RAGResponse(query=query, chunks=[], found=False)

    try:
        results = store.similarity_search_with_score(query, k=k)
        chunks = []
        for doc, score in results:
            meta = doc.metadata
            chunks.append(PolicyChunk(
                content=doc.page_content,
                policy_id=meta.get("policy_id"),
                document_name=meta.get("source"),
                document_version=meta.get("document_version"),
                category=meta.get("category"),
                page=meta.get("page"),
                section=meta.get("section"),
                score=round(float(score), 4),
            ))

        found = len(chunks) > 0
        logger.info("policy_retrieval", query=query[:80], results=len(chunks), found=found)
        return RAGResponse(query=query, chunks=chunks, found=found)
    except Exception as e:
        logger.error("retrieval_error", error=str(e))
        return RAGResponse(query=query, chunks=[], found=False)
