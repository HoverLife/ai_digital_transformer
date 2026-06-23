"""Мини-eval ассистента.

Запуск:  python -m eval.test_cases   (из корня проекта)

Делится на два уровня:
  1) ОФФЛАЙН — детерминированные проверки логики (валидация ИНН). Работают всегда.
  2) ИНТЕГРАЦИОННЫЕ — сквозной прогон через RAG + GigaChat. Требуют:
     - заполненный .env (GIGACHAT_CREDENTIALS);
     - инициализированную базу (python seed.py).
     Если окружение не готово — эти проверки пропускаются (SKIP), а не падают.

Так показывается, что качество выхода осознанно проверяется, а не «на глаз».
"""
from __future__ import annotations

import sys

from app.config import get_settings
from app.inn_utils import is_valid_inn
from app import rag

KOPIRKA = "9709058127"
HOLODILNIK = "7733510051"
UNKNOWN = "7700000016"  # валидная контрольная сумма, но компании нет в базе


# --------------------------------------------------------------------------- #
#  Оффлайн-проверки
# --------------------------------------------------------------------------- #
def test_inn_validation() -> None:
    assert is_valid_inn(KOPIRKA), "валидный 10-значный ИНН должен проходить"
    assert is_valid_inn(HOLODILNIK)
    assert not is_valid_inn("12345"), "короткий ИНН невалиден"
    assert not is_valid_inn("abcdefghij"), "буквы невалидны"
    assert not is_valid_inn("7733510052"), "битая контрольная сумма невалидна"


# --------------------------------------------------------------------------- #
#  Интеграционные проверки
# --------------------------------------------------------------------------- #
def _require_integration() -> None:
    if not get_settings().gigachat_credentials:
        raise SkipTest("GIGACHAT_CREDENTIALS не задан")
    if not rag.collection_exists():
        raise SkipTest("База знаний пуста — запустите python seed.py")


def test_unknown_inn_not_found() -> None:
    """Несуществующий ИНН -> честное 'не найдено', БЕЗ вызова LLM."""
    _require_integration()
    from app.graph import run_analysis

    resp = run_analysis(UNKNOWN)
    assert resp.found is False, "неизвестный ИНН не должен находиться"
    assert resp.mode1 is None and resp.mode2 is None, "LLM не должен вызываться"


def test_mode1_recommendations() -> None:
    """Режим 1: компания найдена, есть боли и проекты."""
    _require_integration()
    from app.graph import run_analysis

    resp = run_analysis(HOLODILNIK)
    assert resp.found and resp.company is not None
    assert resp.mode == 1 and resp.mode1 is not None
    assert 3 <= len(resp.mode1.pains) <= 6, "ожидаем 3–5 болей"
    assert 1 <= len(resp.mode1.projects) <= 3, "ожидаем 1–3 проекта"
    assert all(p.steps for p in resp.mode1.projects), "у проекта должны быть шаги"


def test_mode2_weak_idea_rejected() -> None:
    """Режим 2: заведомо нерелевантная идея НЕ должна получать вердикт 'реализовать'."""
    _require_integration()
    from app.graph import run_analysis

    idea = "Запустить собственную криптобиржу и майнинг-ферму на базе копировальных центров."
    resp = run_analysis(KOPIRKA, idea)
    assert resp.found and resp.mode == 2 and resp.mode2 is not None
    rec = resp.mode2.verdict.recommendation
    assert rec in {"доработать", "отказаться"}, f"слабую идею не стоит 'реализовать' (получено: {rec})"


# --------------------------------------------------------------------------- #
#  Простой раннер (без зависимости от pytest)
# --------------------------------------------------------------------------- #
class SkipTest(Exception):
    pass


def main() -> int:
    tests = [
        test_inn_validation,
        test_unknown_inn_not_found,
        test_mode1_recommendations,
        test_mode2_weak_idea_rejected,
    ]
    passed = skipped = failed = 0
    for t in tests:
        name = t.__name__
        try:
            t()
            print(f"[PASS] {name}")
            passed += 1
        except SkipTest as s:
            print(f"[SKIP] {name}: {s}")
            skipped += 1
        except AssertionError as a:
            print(f"[FAIL] {name}: {a}")
            failed += 1
        except Exception as e:  # noqa: BLE001
            print(f"[ERROR] {name}: {e}")
            failed += 1

    print(f"\nИтог: {passed} passed, {skipped} skipped, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
