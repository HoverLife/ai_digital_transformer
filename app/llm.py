"""Обёртка над GigaChat для получения структурированного (JSON) ответа.

GigaChat не всегда возвращает идеальный JSON, поэтому:
1) аккуратно извлекаем JSON из ответа (срезаем markdown-обёртки и текст вокруг);
2) валидируем в Pydantic-модель;
3) при неудаче делаем один «ремонтный» проход — просим модель починить JSON.
"""
from __future__ import annotations

import re
from typing import Type, TypeVar

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel
from tenacity import retry, stop_after_attempt, wait_exponential

from .gigachat_client import get_chat_model

T = TypeVar("T", bound=BaseModel)


def _extract_json(text: str) -> str:
    """Достаёт JSON-объект из произвольного ответа модели."""
    text = (text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1 and end > start:
        text = text[start : end + 1]
    return text


def _content_to_str(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):  # на случай мультимодального формата
        return " ".join(
            part.get("text", "") if isinstance(part, dict) else str(part)
            for part in content
        )
    return str(content)


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
def _invoke(messages):
    """Вызов модели с ретраями на сетевые сбои."""
    return get_chat_model().invoke(messages)


def generate_structured(system_prompt: str, user_prompt: str, schema: Type[T]) -> T:
    messages = [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]
    resp = _invoke(messages)
    raw = _content_to_str(resp.content)

    try:
        return schema.model_validate_json(_extract_json(raw))
    except Exception as err:  # noqa: BLE001 — нужен любой сбой валидации
        repair = (
            "Твой предыдущий ответ не является валидным JSON по требуемой схеме.\n"
            f"Ошибка валидации: {err}\n"
            "Верни ТОЛЬКО исправленный валидный JSON по той же схеме, без пояснений и markdown."
        )
        messages += [resp, HumanMessage(content=repair)]
        resp2 = _invoke(messages)
        raw2 = _content_to_str(resp2.content)
        return schema.model_validate_json(_extract_json(raw2))
