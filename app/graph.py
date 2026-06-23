"""LangGraph-пайплайн анализа.

Граф:
    validate ──(невалидный ИНН)──────────────► END
        │ valid
    lookup ────(ИНН не найден в базе)────────► END
        │ found
    retrieve (семантический подбор кейсов)
        ├─ idea пустая ──► mode1 (рекомендации) ──► END
        └─ idea задана ──► mode2 (анализ идеи)  ──► END

Узлы — обычные функции; ветвления — conditional edges. Если на ранних шагах в
состояние уже положен `response` (ошибка/не найдено), LLM не вызывается вообще.
"""
from __future__ import annotations

from typing import List, Optional, TypedDict

from langgraph.graph import END, StateGraph

from . import prompts, rag
from .inn_utils import MSG_BAD_FORMAT, MSG_NOT_FOUND, has_valid_format, normalize_inn
from .llm import generate_structured
from .schemas import AnalyzeResponse, CompanyInfo, Mode1Result, Mode2Result


class GraphState(TypedDict, total=False):
    inn: str
    idea: Optional[str]
    mode: int
    company: Optional[CompanyInfo]
    cases: List[dict]
    response: Optional[AnalyzeResponse]


def _mode_of(state: GraphState) -> int:
    return 2 if (state.get("idea") or "").strip() else 1


# --------------------------------------------------------------------------- #
#  Узлы
# --------------------------------------------------------------------------- #
def validate_node(state: GraphState) -> GraphState:
    inn = normalize_inn(state.get("inn", ""))
    mode = _mode_of(state)
    if not has_valid_format(inn):
        return {
            "inn": inn,
            "mode": mode,
            "response": AnalyzeResponse(inn=inn, mode=mode, found=False, message=MSG_BAD_FORMAT),
        }
    return {"inn": inn, "mode": mode}


def lookup_node(state: GraphState) -> GraphState:
    company = rag.find_company_by_inn(state["inn"])
    if company is None:
        return {
            "response": AnalyzeResponse(
                inn=state["inn"], mode=state["mode"], found=False, message=MSG_NOT_FOUND
            )
        }
    return {"company": company}


def retrieve_node(state: GraphState) -> GraphState:
    company = state["company"]
    if state["mode"] == 2:
        query = f"Отрасль: {company.industry}. Компания: {company.name}. Идея проекта: {state.get('idea', '')}"
    else:
        query = f"Отрасль: {company.industry}. Компания: {company.name}. {company.description}"
    return {"cases": rag.search_cases(query, industry=company.industry)}


def mode1_node(state: GraphState) -> GraphState:
    company, cases = state["company"], state.get("cases", [])
    result = generate_structured(
        prompts.SYSTEM_PROMPT,
        prompts.build_mode1_prompt(company, cases),
        Mode1Result,
    )
    return {
        "response": AnalyzeResponse(
            inn=state["inn"],
            mode=1,
            found=True,
            company=company,
            retrieved_cases=[c.get("title", "") for c in cases],
            mode1=result,
        )
    }


def mode2_node(state: GraphState) -> GraphState:
    company, cases = state["company"], state.get("cases", [])
    result = generate_structured(
        prompts.SYSTEM_PROMPT,
        prompts.build_mode2_prompt(company, cases, state.get("idea", "")),
        Mode2Result,
    )
    return {
        "response": AnalyzeResponse(
            inn=state["inn"],
            mode=2,
            found=True,
            company=company,
            retrieved_cases=[c.get("title", "") for c in cases],
            mode2=result,
        )
    }


# --------------------------------------------------------------------------- #
#  Маршрутизация
# --------------------------------------------------------------------------- #
def _after_validate(state: GraphState) -> str:
    return END if state.get("response") is not None else "lookup"


def _after_lookup(state: GraphState) -> str:
    return END if state.get("response") is not None else "retrieve"


def _after_retrieve(state: GraphState) -> str:
    return "mode2" if state["mode"] == 2 else "mode1"


def build_graph():
    g = StateGraph(GraphState)
    g.add_node("validate", validate_node)
    g.add_node("lookup", lookup_node)
    g.add_node("retrieve", retrieve_node)
    g.add_node("mode1", mode1_node)
    g.add_node("mode2", mode2_node)

    g.set_entry_point("validate")
    g.add_conditional_edges("validate", _after_validate, {"lookup": "lookup", END: END})
    g.add_conditional_edges("lookup", _after_lookup, {"retrieve": "retrieve", END: END})
    g.add_conditional_edges("retrieve", _after_retrieve, {"mode1": "mode1", "mode2": "mode2"})
    g.add_edge("mode1", END)
    g.add_edge("mode2", END)
    return g.compile()


# Компилируется один раз на процесс (LLM/Qdrant дёргаются лениво внутри узлов).
GRAPH = build_graph()


def run_analysis(inn: str, idea: Optional[str] = None) -> AnalyzeResponse:
    final_state = GRAPH.invoke({"inn": inn, "idea": idea})
    return final_state["response"]
