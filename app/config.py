"""Конфигурация приложения. Все секреты и параметры читаются из .env."""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- GigaChat ---
    gigachat_credentials: str = ""           # Authorization key (base64 client_id:secret)
    gigachat_scope: str = "GIGACHAT_API_PERS"
    gigachat_model: str = "GigaChat"          # GigaChat (Lite) | GigaChat-Pro | GigaChat-Max
    gigachat_embeddings_model: str = "EmbeddingsGigaR"  # или "Embeddings"
    gigachat_verify_ssl: bool = False

    # --- Qdrant ---
    # Вариант A (локальный контейнер): host+port, api_key не нужен.
    # Вариант B (Qdrant Cloud): задать qdrant_url (полный https URL c :6333) + qdrant_api_key.
    qdrant_url: str = ""          # напр. https://<id>.gcp.cloud.qdrant.io:6333
    qdrant_api_key: str = ""      # только для Qdrant Cloud
    qdrant_host: str = "localhost"
    qdrant_port: int = 6333
    qdrant_collection: str = "transform_kb"

    # --- RAG ---
    rag_top_k: int = 5

    # --- Запуск ---
    # Если true — при старте приложение само заполнит базу (seed), когда коллекции нет
    # ИЛИ версия данных устарела. Делает `docker compose up` полноценным «одной командой».
    seed_on_start: bool = True

    def resolve_qdrant_url(self) -> str:
        """Полный URL: явный qdrant_url (Cloud) имеет приоритет над host:port (контейнер)."""
        return self.qdrant_url or f"http://{self.qdrant_host}:{self.qdrant_port}"


@lru_cache
def get_settings() -> Settings:
    """Singleton-настройки (кэшируются, чтобы .env читался один раз)."""
    return Settings()
