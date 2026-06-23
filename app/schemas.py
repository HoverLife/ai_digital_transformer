"""Pydantic-схемы запросов и структурированных ответов LLM."""
from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field


# --------------------------------------------------------------------------- #
#  Запрос
# --------------------------------------------------------------------------- #
class AnalyzeRequest(BaseModel):
    inn: str = Field(..., description="ИНН компании (10 или 12 цифр)")
    idea: Optional[str] = Field(
        None, description="Опциональная идея проекта. Если задана — включается Режим 2."
    )


# --------------------------------------------------------------------------- #
#  Карточка компании (из RAG)
# --------------------------------------------------------------------------- #
class Fact(BaseModel):
    label: str
    value: str


class CompanyInfo(BaseModel):
    inn: str
    name: str
    full_name: Optional[str] = None
    industry: str
    description: str
    summary: Optional[str] = None
    facts: List[Fact] = Field(default_factory=list)
    services: List[str] = Field(default_factory=list)
    clients: List[str] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
#  Режим 1 — рекомендации
# --------------------------------------------------------------------------- #
class TransformationProject(BaseModel):
    title: str = Field(..., description="Название проекта")
    essence: str = Field(..., description="Суть проекта")
    pain_addressed: str = Field(..., description="Какую боль закрывает")
    steps: List[str] = Field(..., description="Шаги внедрения")
    expected_effect: str = Field(..., description="Ожидаемый эффект")


class Mode1Result(BaseModel):
    pains: List[str] = Field(..., description="3–5 болей компании")
    projects: List[TransformationProject] = Field(..., description="1–3 проекта")


# --------------------------------------------------------------------------- #
#  Режим 2 — строгий анализ идеи
# --------------------------------------------------------------------------- #
class Realism(BaseModel):
    risks: List[str]
    constraints: List[str]
    dependencies: List[str]


class Verdict(BaseModel):
    recommendation: Literal["реализовать", "доработать", "отказаться"]
    score: int = Field(..., ge=1, le=10, description="Итоговая оценка 1–10")
    rationale: str = Field(..., description="Обоснование вердикта")


class Mode2Result(BaseModel):
    relevance: str = Field(..., description="Насколько идея актуальна для компании и почему")
    pains_addressed: List[str] = Field(..., description="Какие боли закрывает")
    pains_not_addressed: List[str] = Field(..., description="Какие боли НЕ закрывает")
    realism: Realism = Field(..., description="Реалистичность внедрения")
    verdict: Verdict
    improvements: List[str] = Field(
        ..., description="Что доработать или чем заменить, если идея слабая"
    )


# --------------------------------------------------------------------------- #
#  Ответ API
# --------------------------------------------------------------------------- #
class AnalyzeResponse(BaseModel):
    inn: str
    mode: Literal[1, 2]
    found: bool = Field(..., description="Найдена ли компания в базе знаний")
    message: Optional[str] = Field(None, description="Пояснение (напр. компания не найдена)")
    company: Optional[CompanyInfo] = None
    retrieved_cases: List[str] = Field(
        default_factory=list, description="Заголовки кейсов из RAG, использованных как контекст"
    )
    mode1: Optional[Mode1Result] = None
    mode2: Optional[Mode2Result] = None
