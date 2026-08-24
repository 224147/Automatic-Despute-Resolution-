from __future__ import annotations

from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    app_name: str = "dispute-resolution"
    app_env: str = "development"
    debug: bool = False
    secret_key: str = "change-me-in-production"
    api_v1_prefix: str = "/api/v1"

    # Database
    database_url: str = "sqlite+aiosqlite:///./dispute.db"
    database_echo: bool = False

    # JWT
    jwt_secret_key: str = "change-me-jwt-secret-key"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 30

    # LLM
    llm_provider: str = "openai"
    openai_api_key: str = ""
    llm_model: str = "gpt-4o-mini"
    llm_temperature: float = 0.0

    # Embeddings
    embedding_provider: str = "sentence-transformers"
    embedding_model: str = "all-MiniLM-L6-v2"

    # Vector Store
    vector_store_type: str = "faiss"
    vector_store_path: str = "data/vector_store"

    # RAG
    rag_chunk_size: int = 500
    rag_chunk_overlap: int = 50
    rag_top_k: int = 5

    # LangSmith
    langchain_tracing_v2: bool = False
    langchain_api_key: str = ""
    langchain_project: str = "dispute-resolution"

    # CORS
    cors_origins: list[str] = Field(default=["http://localhost:3000", "http://localhost:8501"])

    # Logging
    log_level: str = "INFO"
    log_format: str = "json"

    # Classification
    classification_confidence_threshold: float = 0.7

    # Risk
    high_value_threshold: float = 50000.0

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "case_sensitive": False}


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
