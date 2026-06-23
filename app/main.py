"""FastAPI-приложение: REST API + раздача простого фронтенда."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from . import rag
from .config import get_settings
from .graph import run_analysis
from .inn_utils import MSG_BAD_FORMAT, MSG_NOT_FOUND, has_valid_format, normalize_inn
from .schemas import AnalyzeRequest, AnalyzeResponse

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ai-transform-assistant")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    settings = get_settings()
    if settings.seed_on_start:
        # Решаем гонку с контейнером qdrant: ждём, пока он реально поднимется.
        if not rag.wait_until_ready():
            logger.warning("Qdrant не ответил вовремя — пропускаю авто-сид. Запустите: python seed.py")
        elif rag.get_kb_version() != rag.KB_VERSION:  # нет коллекции или устаревшая версия
            try:
                import seed  # noqa: PLC0415 — ленивый импорт скрипта сидирования

                logger.info("SEED_ON_START: база отсутствует/устарела, (пере)заполняю базу знаний...")
                seed.main()
                logger.info("SEED_ON_START: база знаний готова.")
            except Exception as exc:  # noqa: BLE001
                logger.warning("Авто-сид не выполнен (%s). Запустите: python seed.py", exc)

    logger.info("=" * 60)
    logger.info("  Сервис запущен. Откройте в браузере:  http://localhost:8000")
    logger.info("=" * 60)
    yield


app = FastAPI(
    title="AI-ассистент цифровой трансформации",
    version="1.1.0",
    description="RAG (GigaChat + Qdrant + LangGraph): ИНН → боли и проекты / анализ идеи.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict:
    settings = get_settings()
    return {
        "status": "ok",
        "qdrant_url": settings.resolve_qdrant_url(),
        "collection": settings.qdrant_collection,
        "collection_ready": rag.collection_exists(),
        "model": settings.gigachat_model,
        "credentials_set": bool(settings.gigachat_credentials),
    }


@app.get("/api/companies")
def companies() -> dict:
    """Список компаний в базе знаний (для обзора и быстрого выбора в UI)."""
    if not rag.collection_exists():
        return {"companies": []}
    try:
        return {"companies": rag.list_companies()}
    except Exception:  # noqa: BLE001
        return {"companies": []}


@app.post("/api/analyze", response_model=AnalyzeResponse)
def analyze(req: AnalyzeRequest) -> AnalyzeResponse:
    if not rag.collection_exists():
        raise HTTPException(
            status_code=503,
            detail="База знаний не инициализирована. Запустите: python seed.py",
        )
    import time

    started = time.perf_counter()
    try:
        result = run_analysis(req.inn, req.idea)
        logger.info(
            "analyze inn=%s mode=%s found=%s за %.2fs",
            normalize_inn(req.inn), 2 if (req.idea or "").strip() else 1,
            result.found, time.perf_counter() - started,
        )
        return result
    except Exception as exc:  # noqa: BLE001
        logger.exception("Ошибка анализа")
        raise HTTPException(status_code=502, detail=f"Ошибка обращения к LLM/хранилищу: {exc}")


@app.get("/api/company/{inn}")
def company(inn: str) -> dict:
    """Быстрый lookup досье компании по ИНН (без LLM) — UI рисует его сразу."""
    norm = normalize_inn(inn)
    if not has_valid_format(norm):
        return {"found": False, "message": MSG_BAD_FORMAT}
    if not rag.collection_exists():
        raise HTTPException(status_code=503, detail="База знаний не инициализирована. Запустите: python seed.py")
    found = rag.find_company_by_inn(norm)
    if found is None:
        return {"found": False, "message": MSG_NOT_FOUND}
    return {"found": True, "company": found.model_dump()}


# Раздача фронтенда (index.html) из app/static на корне.
_STATIC_DIR = Path(__file__).parent / "static"
app.mount("/", StaticFiles(directory=str(_STATIC_DIR), html=True), name="static")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=False)
