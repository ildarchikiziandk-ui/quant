#!/usr/bin/env bash
# Нува на нейросети GigaChat. Запуск: bash /opt/nuvora/deploy/set-gigachat.sh [КЛЮЧ_АВТОРИЗАЦИИ]
# Ключ: developers.sber.ru → «GigaChat API» → проект → «Получить ключ» (скопируйте «Authorization key»).
# Для физлиц есть бесплатный лимит (scope GIGACHAT_API_PERS).
set -euo pipefail
APP_DIR=/opt/nuvora
ENV="$APP_DIR/.env"
KEY="${1:-}"
[ -n "$KEY" ] || { read -rsp "Ключ авторизации GigaChat (символы не видны): " KEY; echo; }
SCOPE="${GIGACHAT_SCOPE:-GIGACHAT_API_PERS}"

echo "==> Сертификат НУЦ Минцифры (им подписан сервер GigaChat)"
CERTS="$APP_DIR/data/certs"; mkdir -p "$CERTS"
curl -fsSL https://gu-st.ru/content/lending/russian_trusted_root_ca_pem.crt -o "$CERTS/russian_root.pem"
curl -fsSL https://gu-st.ru/content/lending/russian_trusted_sub_ca_pem.crt -o "$CERTS/russian_sub.pem" || true
SYS=/etc/ssl/certs/ca-certificates.crt
cat "$SYS" "$CERTS/russian_root.pem" $( [ -s "$CERTS/russian_sub.pem" ] && echo "$CERTS/russian_sub.pem" ) > "$CERTS/gigachat-ca.pem"

echo "==> Проверяю ключ"
CODE=$(curl -s -o /tmp/giga-oauth.json -w "%{http_code}" --cacert "$CERTS/gigachat-ca.pem" -X POST https://ngw.devices.sberbank.ru:9443/api/v2/oauth \
  -H "Authorization: Basic $KEY" -H "RqUID: $(cat /proc/sys/kernel/random/uuid)" -H "Content-Type: application/x-www-form-urlencoded" -d "scope=$SCOPE" || true)
if [ "$CODE" != "200" ]; then
  echo "   GigaChat ответил кодом $CODE — проверьте ключ и scope ($SCOPE). Ответ: $(head -c 300 /tmp/giga-oauth.json)"; rm -f /tmp/giga-oauth.json; exit 1
fi
TOKEN=$(python3 -c "import json;print(json.load(open('/tmp/giga-oauth.json'))['access_token'])" 2>/dev/null || true)
echo "   ключ работает"
if [ -n "$TOKEN" ]; then
  M=$(curl -s -o /dev/null -w "%{http_code}" --cacert "$CERTS/gigachat-ca.pem" https://api.giga.chat/v1/models -H "Accept: application/json" -H "Authorization: Bearer $TOKEN" || true)
  echo "   список моделей: код $M (200 — всё в порядке)"
fi
rm -f /tmp/giga-oauth.json

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
set_var GIGACHAT_AUTH_KEY "$KEY"
set_var GIGACHAT_SCOPE "$SCOPE"
set_var GIGACHAT_CA "$CERTS/gigachat-ca.pem"
chown -R nuvora:nuvora "$APP_DIR/data" 2>/dev/null || true
chown nuvora:nuvora "$ENV" 2>/dev/null || true; chmod 600 "$ENV"
systemctl restart nuvora
echo "Готово! Нува теперь отвечает с помощью GigaChat. Без связи с GigaChat она по-прежнему отвечает по справке."
