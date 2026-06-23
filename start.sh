#!/usr/bin/env bash
# Запуск всего проекта одной командой: поднимает контейнеры, ждёт готовности
# и открывает сайт в браузере. Работает в Git Bash (Windows), macOS и Linux.
set -e
URL="http://localhost:8000"

echo "▸ Поднимаю сервисы (docker compose up)..."
docker compose up -d --build

echo "▸ Жду готовности $URL ..."
for _ in $(seq 1 60); do
  if curl -fs "$URL/api/health" >/dev/null 2>&1; then
    echo "  сервис готов."
    break
  fi
  sleep 2
done

echo "▸ Открываю сайт в браузере..."
case "$(uname -s)" in
  MINGW*|MSYS*|CYGWIN*) cmd.exe /c start "" "$URL" ;;
  Darwin)               open "$URL" ;;
  *)                    xdg-open "$URL" >/dev/null 2>&1 || true ;;
esac

echo "▸ Готово. Логи ниже (Ctrl+C — выйти). Остановить всё: docker compose down"
docker compose logs -f app
