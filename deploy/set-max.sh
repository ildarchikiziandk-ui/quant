#!/usr/bin/env bash
# Бот в мессенджере MAX для проверки номера телефона. Запуск: bash /opt/nuvora/deploy/set-max.sh
# Сначала создайте бота: в MAX откройте @MasterBot (max.ru/MasterBot), создайте бота и получите токен.
set -euo pipefail
APP_DIR=/opt/nuvora
ENV="$APP_DIR/.env"
API="https://platform-api2.max.ru"

echo "Проверяю связь с MAX…"
if ! curl -s -o /dev/null --max-time 10 "$API/me"; then
  echo "Сервер не достучался до $API. Проверьте интернет на сервере и запустите снова."; exit 1
fi
echo "Вставьте токен бота от @MasterBot. Символы при вводе не видны (на телефоне — долгое нажатие → «Вставить»)."
read -rsp "Токен: " TOKEN; echo
TOKEN=$(printf '%s' "$TOKEN" | tr -d '[:space:]')
echo "Получено символов: ${#TOKEN}"
[ -n "$TOKEN" ] || { echo "Токен пустой — похоже, вставка не сработала. Запустите снова."; exit 1; }
CODE=$(curl -s -o /tmp/max-me.json -w "%{http_code}" --max-time 10 -H "Authorization: $TOKEN" "$API/me" || true)
if [ "$CODE" != "200" ]; then
  echo "MAX не принял токен (ответ $CODE). Скопируйте токен в @MasterBot ещё раз."; rm -f /tmp/max-me.json; exit 1
fi
NAME=$(python3 -c "import json; d=json.load(open('/tmp/max-me.json')); print(d.get('username') or '')" 2>/dev/null || true)
rm -f /tmp/max-me.json
if [ -z "$NAME" ]; then read -rp "Логин бота в MAX (например, nuvora_check_bot): " NAME; fi
NAME=${NAME#@}

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
set_var MAX_BOT_TOKEN "$TOKEN"
set_var MAX_BOT_USERNAME "$NAME"
chown nuvora:nuvora "$ENV"; chmod 600 "$ENV"
systemctl restart nuvora
echo "Готово: бот $NAME подключён. Проверка номера включается в админ-панели → Сайт."
