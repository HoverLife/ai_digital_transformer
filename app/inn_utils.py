"""Валидация ИНН: формат + контрольная сумма (10- и 12-значные)."""
from __future__ import annotations

_W10 = [2, 4, 10, 3, 5, 9, 4, 6, 8]
_W11 = [7, 2, 4, 10, 3, 5, 9, 4, 6, 8]
_W12 = [3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8]

# Пользовательские сообщения (единый источник для API и графа)
MSG_BAD_FORMAT = "Некорректный ИНН: ожидается 10 или 12 цифр."
MSG_NOT_FOUND = (
    "Информации об этой компании нет в базе знаний. "
    "Воспользуйтесь готовыми компаниями из списка выше."
)


def has_valid_format(inn: str) -> bool:
    """Только формат: 10 или 12 цифр. Используется для пользовательского флоу —
    несовпадение контрольной суммы трактуем как «нет в базе», а не как ошибку ввода."""
    return bool(inn) and inn.isdigit() and len(inn) in (10, 12)


def _csum(digits: list[int], weights: list[int]) -> int:
    return sum(d * w for d, w in zip(digits, weights)) % 11 % 10


def is_valid_inn(inn: str) -> bool:
    """True, если ИНН синтаксически валиден (длина, цифры, контрольная сумма)."""
    if not inn or not inn.isdigit():
        return False
    d = [int(c) for c in inn]
    if len(inn) == 10:
        return _csum(d[:9], _W10) == d[9]
    if len(inn) == 12:
        return _csum(d[:10], _W11) == d[10] and _csum(d[:11], _W12) == d[11]
    return False


def normalize_inn(inn: str) -> str:
    """Убираем пробелы и прочее, оставляя только цифры."""
    return "".join(ch for ch in (inn or "") if ch.isdigit())
