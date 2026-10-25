#!/usr/bin/env bash
# Ключи магазина ЮKassa для покупки Искр и Nuvora+. Запуск: bash /opt/nuvora/deploy/set-payments.sh [SHOP_ID] [SECRET]
# Магазин заводится на yookassa.ru (подходит и самозанятым). После ключей включите оплату: Админ-панель → «Сайт и группы».
# В личном кабинете ЮKassa укажите адрес для уведомлений: <адрес сайта>/buy/webhook (событие payment.succeeded).
set -euo pipefail
APP_DIR=/opt/nuvora
ENV="$APP_DIR/.env"
ID="${1:-}"; SECRET="${2:-}"
[ -n "$ID" ] || read -rp "shopId: " ID
[ -n "$SECRET" ] || { read -rsp "Секретный ключ (символы не видны): " SECRET; echo; }
SITE=$(grep -E '^SITE_URL=' "$ENV" | tail -1 | cut -d= -f2- | tr -d '"' | sed 's#/$##')
SITE=${SITE:-https://nvra.ru}
set_var() {
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
set_var YOOKASSA_SHOP_ID "$ID"
set_var YOOKASSA_SECRET "$SECRET"
chown nuvora:nuvora "$ENV" 2>/dev/null || true; chmod 600 "$ENV"
systemctl restart nuvora
echo "Готово. Ключи сохранены. Включите оплату: $SITE/admin/site → «Оплата Искр и Nuvora+»."
echo "Адрес для уведомлений в кабинете ЮKassa: $SITE/buy/webhook"
