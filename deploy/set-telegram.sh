#!/usr/bin/env bash
# Telegram-бот для проверки номера телефона. Запуск: bash /opt/nuvora/deploy/set-telegram.sh
# Сначала создайте бота: в Telegram откройте @BotFather → /newbot → имя (например, «Nuvora проверка») и логин (например, nuvora_check_bot).
set -euo pipefail
APP_DIR=/opt/nuvora
ENV="$APP_DIR/.env"
echo "Вставьте токен бота от @BotFather (вида 123456789:AA...). Символы при вводе не видны."
read -rsp "Токен: " TOKEN; echo
INFO=$(curl -s --max-time 10 "https://api.telegram.org/bot${TOKEN}/getMe" || true)
NAME=$(printf '%s' "$INFO" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['result']['username'] if d.get('ok') else '')" 2>/dev/null || true)
if [ -z "$NAME" ]; then echo "Telegram не принял токен (или сервер не достучался до api.telegram.org). Проверьте и запустите снова."; exit 1; fi

set_var() {  # set_var KEY VALUE — заменить или добавить строку в .env
  local key="$1" val="$2"
  if grep -q "^${key}=" "$ENV"; then
    python3 - "$ENV" "$key" "$val" <<'PY'
import sys
path, key, val = sys.argv[1:]
lines = open(path, encoding="utf-8").read().splitlines()
lines = [f"{key}={val}" if l.startswith(key + "=") else l for l in lines]
open(path, "w", encoding="utf-8").write("\n".join(lines) + "\n")
PY
  else
    echo "${key}=${val}" >> "$ENV"
  fi
}
set_var TELEGRAM_BOT_TOKEN "$TOKEN"
set_var TELEGRAM_BOT_USERNAME "$NAME"
chown nuvora:nuvora "$ENV"; chmod 600 "$ENV"
# описание бота, которое видно до нажатия «Начать»
curl -s --max-time 10 "https://api.telegram.org/bot${TOKEN}/setMyDescription" --data-urlencode "description=Бот проверки аккаунтов Nuvora (nvra.ru). Откройте его по ссылке со страницы проверки на сайте и поделитесь номером одной кнопкой." >/dev/null || true
systemctl restart nuvora
echo "Готово: бот @$NAME подключён. Проверка номера включается в админ-панели → Сайт."
