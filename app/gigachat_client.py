"""Фабрики моделей GigaChat (чат + эмбеддинги) через langchain-gigachat.

Один провайдер и для LLM, и для эмбеддингов: единая аутентификация (OAuth по
Authorization key обновляется SDK автоматически) и нативная работа с русским языком.
"""
from __future__ import annotations

from functools import lru_cache

from langchain_gigachat import GigaChat, GigaChatEmbeddings

from .config import get_settings


@lru_cache
def get_chat_model() -> GigaChat:
    s = get_settings()
    if not s.gigachat_credentials:
        raise RuntimeError(
            "GIGACHAT_CREDENTIALS не задан. Заполните .env (см. .env.example)."
        )
    return GigaChat(
        credentials=s.gigachat_credentials,
        scope=s.gigachat_scope,
        model=s.gigachat_model,
        verify_ssl_certs=s.gigachat_verify_ssl,
        profanity_check=False,   # анализ бизнес-идей не должен цензуриться
        timeout=90,
        temperature=0.6,         # выше — для разнообразия и небанальных идей
        max_tokens=2048,
    )


@lru_cache
def get_embeddings() -> GigaChatEmbeddings:
    s = get_settings()
    if not s.gigachat_credentials:
        raise RuntimeError(
            "GIGACHAT_CREDENTIALS не задан. Заполните .env (см. .env.example)."
        )
    return GigaChatEmbeddings(
        credentials=s.gigachat_credentials,
        scope=s.gigachat_scope,
        model=s.gigachat_embeddings_model,
        verify_ssl_certs=s.gigachat_verify_ssl,
    )
