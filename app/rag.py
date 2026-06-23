"""RAG-слой поверх Qdrant.

Ключевая идея — гибридный поиск:
- ИНН это ТОЧНЫЙ идентификатор -> карточка компании достаётся детерминированным
  payload-фильтром (никакой семантики, никаких «похожих» компаний);
- отраслевые кейсы для контекста достаются СЕМАНТИЧЕСКИ (vector search).
"""
from __future__ import annotations

from functools import lru_cache
from typing import List, Optional

from qdrant_client import QdrantClient
from qdrant_client.http import models as qm

from .config import get_settings
from .gigachat_client import get_embeddings
from .schemas import CompanyInfo

TYPE_COMPANY = "company"
TYPE_CASE = "case"
TYPE_META = "_meta"

# Версия базы знаний. Поднимайте при изменении структуры/содержимого data/*.json —
# приложение увидит несовпадение и пересеет базу автоматически (если SEED_ON_START).
KB_VERSION = "2"


@lru_cache
def get_client() -> QdrantClient:
    s = get_settings()
    return QdrantClient(
        url=s.resolve_qdrant_url(),
        api_key=s.qdrant_api_key or None,  # None -> локальный контейнер без авторизации
        timeout=30,
    )


def collection_exists() -> bool:
    s = get_settings()
    try:
        return get_client().collection_exists(s.qdrant_collection)
    except Exception:
        return False


def wait_until_ready(timeout: float = 90.0, interval: float = 1.5) -> bool:
    """Дожидается готовности Qdrant (решает гонку app↔qdrant при docker compose up).

    Соединение, которое ещё не поднялось, отклоняется мгновенно, поэтому опрос дешёвый.
    """
    import time

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            get_client().get_collections()
            return True
        except Exception:
            time.sleep(interval)
    return False


def get_kb_version() -> Optional[str]:
    """Версия загруженной базы знаний (из служебной точки _meta), либо None."""
    s = get_settings()
    try:
        flt = qm.Filter(must=[qm.FieldCondition(key="type", match=qm.MatchValue(value=TYPE_META))])
        points, _ = get_client().scroll(
            collection_name=s.qdrant_collection, scroll_filter=flt, limit=1, with_payload=True
        )
        if points:
            return (points[0].payload or {}).get("version")
    except Exception:
        return None
    return None


def find_company_by_inn(inn: str) -> Optional[CompanyInfo]:
    """Точный lookup компании по ИНН (payload-фильтр type=company, inn=...)."""
    s = get_settings()
    flt = qm.Filter(
        must=[
            qm.FieldCondition(key="type", match=qm.MatchValue(value=TYPE_COMPANY)),
            qm.FieldCondition(key="inn", match=qm.MatchValue(value=inn)),
        ]
    )
    points, _ = get_client().scroll(
        collection_name=s.qdrant_collection,
        scroll_filter=flt,
        limit=1,
        with_payload=True,
    )
    if not points:
        return None
    p = points[0].payload or {}
    return CompanyInfo(
        inn=p["inn"],
        name=p["name"],
        full_name=p.get("full_name"),
        industry=p["industry"],
        description=p["description"],
        summary=p.get("summary"),
        facts=p.get("facts", []),
        services=p.get("services", []),
        clients=p.get("clients", []),
    )


def list_companies() -> List[dict]:
    """Все компании из базы (для UI/обзора): inn, name, industry."""
    s = get_settings()
    out: List[dict] = []
    next_offset = None
    flt = qm.Filter(must=[qm.FieldCondition(key="type", match=qm.MatchValue(value=TYPE_COMPANY))])
    while True:
        points, next_offset = get_client().scroll(
            collection_name=s.qdrant_collection,
            scroll_filter=flt,
            limit=64,
            offset=next_offset,
            with_payload=True,
        )
        for p in points:
            pl = p.payload or {}
            out.append({"inn": pl.get("inn"), "name": pl.get("name"), "industry": pl.get("industry")})
        if next_offset is None:
            break
    return sorted(out, key=lambda c: c["name"] or "")


def _case_filter(industry: Optional[str] = None) -> qm.Filter:
    must = [qm.FieldCondition(key="type", match=qm.MatchValue(value=TYPE_CASE))]
    if industry:
        must.append(qm.FieldCondition(key="industry", match=qm.MatchValue(value=industry)))
    return qm.Filter(must=must)


def search_cases(query_text: str, industry: Optional[str] = None, k: Optional[int] = None) -> List[dict]:
    """Отраслево-осознанный семантический поиск кейсов.

    Сначала берём наиболее релевантные кейсы ИМЕННО этой отрасли, затем добираем
    до k штук семантически близкими кейсами из всей базы (включая кросс-индустриальные).
    """
    s = get_settings()
    k = k or s.rag_top_k
    client = get_client()
    vector = get_embeddings().embed_query(query_text)

    collected: list = []
    seen: set = set()

    def _add(points):
        for pt in points:
            if pt.id not in seen:
                seen.add(pt.id)
                collected.append(pt)

    # Tier 1 — кейсы той же отрасли (приоритет).
    if industry:
        r1 = client.query_points(
            collection_name=s.qdrant_collection,
            query=vector,
            query_filter=_case_filter(industry),
            limit=k,
            with_payload=True,
        )
        _add(r1.points)

    # Tier 2 — добор семантикой по всей базе кейсов.
    if len(collected) < k:
        r2 = client.query_points(
            collection_name=s.qdrant_collection,
            query=vector,
            query_filter=_case_filter(),
            limit=k * 2,
            with_payload=True,
        )
        _add(r2.points)

    return [pt.payload or {} for pt in collected[:k]]
