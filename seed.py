"""Загрузка базы знаний в Qdrant.

Запуск:  python seed.py
(в Docker: docker compose exec app python seed.py)

- читает data/companies.json и data/knowledge/cases.json;
- эмбеддит тексты через GigaChat Embeddings;
- (пере)создаёт коллекцию Qdrant с автоопределением размерности вектора;
- грузит точки двух типов: company (для точного lookup по ИНН) и case (для семантики).
"""
from __future__ import annotations

import json
from pathlib import Path

from qdrant_client.http import models as qm

from app.config import get_settings
from app.gigachat_client import get_embeddings
from app.rag import KB_VERSION, TYPE_CASE, TYPE_COMPANY, TYPE_META, get_client

DATA_DIR = Path(__file__).parent / "data"


def _load(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def _company_text(c: dict) -> str:
    return f"{c['name']}. Отрасль: {c['industry']}. {c['description']}"


def _case_text(c: dict) -> str:
    if c.get("text"):
        return c["text"]
    return (
        f"{c.get('title', '')}. Боль: {c.get('pain', '')} "
        f"Решение: {c.get('solution', '')} Эффект: {c.get('effect', '')}"
    )


def main() -> None:
    settings = get_settings()
    client = get_client()
    embeddings = get_embeddings()

    companies = _load(DATA_DIR / "companies.json")
    cases = _load(DATA_DIR / "knowledge" / "cases.json")
    print(f"Загружаю {len(companies)} компаний и {len(cases)} кейсов...")

    print("Считаю эмбеддинги через GigaChat...")
    company_vectors = embeddings.embed_documents([_company_text(c) for c in companies])
    case_vectors = embeddings.embed_documents([_case_text(c) for c in cases])

    dim = len(company_vectors[0])
    print(f"Размерность эмбеддингов: {dim}")

    # (Пере)создаём коллекцию — сид идемпотентен.
    if client.collection_exists(settings.qdrant_collection):
        client.delete_collection(settings.qdrant_collection)
    client.create_collection(
        collection_name=settings.qdrant_collection,
        vectors_config=qm.VectorParams(size=dim, distance=qm.Distance.COSINE),
    )
    # Индексы по полям, по которым фильтруем (точный lookup и фильтры).
    for field in ("type", "inn", "industry"):
        client.create_payload_index(
            collection_name=settings.qdrant_collection,
            field_name=field,
            field_schema=qm.PayloadSchemaType.KEYWORD,
        )

    points: list[qm.PointStruct] = []
    pid = 0
    for company, vector in zip(companies, company_vectors):
        points.append(
            qm.PointStruct(id=pid, vector=vector, payload={"type": TYPE_COMPANY, **company})
        )
        pid += 1
    for case, vector in zip(cases, case_vectors):
        points.append(
            qm.PointStruct(id=pid, vector=vector, payload={"type": TYPE_CASE, **case})
        )
        pid += 1

    # Служебная точка с версией базы знаний (для самоисцеляющегося авто-сида).
    points.append(
        qm.PointStruct(id=999_999, vector=[0.0] * dim, payload={"type": TYPE_META, "version": KB_VERSION})
    )

    client.upsert(collection_name=settings.qdrant_collection, points=points)
    print(
        f"Готово: в коллекцию '{settings.qdrant_collection}' загружено "
        f"{len(companies)} компаний и {len(cases)} кейсов (версия базы знаний: {KB_VERSION})."
    )


if __name__ == "__main__":
    main()
