"""Shared LLM factory for all agents."""
from __future__ import annotations

from langchain_core.language_models import BaseChatModel

from app.core.config import get_settings


def get_llm() -> BaseChatModel:
    settings = get_settings()
    if settings.llm_provider == "groq" and settings.groq_api_key:
        from langchain_groq import ChatGroq
        return ChatGroq(
            model=settings.llm_model,
            temperature=settings.llm_temperature,
            api_key=settings.groq_api_key,
        )
    if settings.openai_api_key:
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=settings.llm_model,
            temperature=settings.llm_temperature,
            api_key=settings.openai_api_key,
        )
    raise RuntimeError("No LLM provider configured. Set GROQ_API_KEY or OPENAI_API_KEY.")
