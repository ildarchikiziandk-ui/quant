#!/usr/bin/env bash
# Включает вход через Яндекс ID. Запуск: bash /opt/nuvora/deploy/set-yandex.sh [CLIENT_ID] [CLIENT_SECRET]
# Ключи берутся на oauth.yandex.ru. Redirect URI там должен быть ровно: <адрес сайта>/auth/yandex/callback
set -euo pipefail
APP_DIR=/opt/nuvora
ENV="$APP_DIR/.env"
ID="${1:-}"; SECRET="${2:-}"
[ -n "$ID" ] || read -rp "Client ID: " ID
[ -n "$SECRET" ] || { read -rsp "Client secret (символы не видны): " SECRET; echo; }
SITE=$(grep -E '^SITE_URL=' "$ENV" | tail -1 | cut -d= -f2- | tr -d '"' | sed 's#/$##')
SITE=${SITE:-https://nvra.ru}

set_var() {  # заменить или добавить строку KEY=VALUE в .env
  python3 - "$ENV" "$1" "$2" <<'PY'
import sys
path, key, val = sys.argv[1:]
lines = open(path, encoding="utf-8").read().splitlines()
if any(l.startswith(key + "=") for l in lines):
    lines = [f"{key}={val}" if l.startswith(key + "=") else l for l in lines]
else:
    lines.append(f"{key}={val}")
open(path, "w", encoding="utf-8").write("\n".join(lines) + "\n")
PY
}
set_var YANDEX_CLIENT_ID "$ID"
set_var YANDEX_CLIENT_SECRET "$SECRET"
set_var YANDEX_REDIRECT_URI "$SITE/auth/yandex/callback"
chown nuvora:nuvora "$ENV" 2>/dev/null || true; chmod 600 "$ENV"
systemctl restart nuvora
echo "Готово. Вход через Яндекс включён."
echo "Проверьте в настройках приложения на oauth.yandex.ru: Redirect URI = $SITE/auth/yandex/callback"
