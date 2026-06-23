FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install -r requirements.txt

# GigaChat использует сертификаты УЦ Минцифры РФ, которых нет в стандартном trust-store.
# Добавляем корневой сертификат в bundle certifi (его использует httpx внутри SDK).
# Шаг best-effort: если скачать не удалось, сборка не падает — это нужно лишь при
# GIGACHAT_VERIFY_SSL=true (по умолчанию false).
RUN curl -fsSL https://gu-st.ru/content/Other/doc/russiantrustedca.pem -o /tmp/russian_ca.pem \
      && cat /tmp/russian_ca.pem >> "$(python -m certifi)" \
      && echo "Russian Trusted Root CA добавлен в certifi" \
      || echo "WARN: Russian CA не установлен (ок при GIGACHAT_VERIFY_SSL=false)"

COPY app ./app
COPY data ./data
COPY seed.py .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
