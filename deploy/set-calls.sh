#!/usr/bin/env bash
# Ретранслятор для звонков (coturn). Нужен, когда собеседники не могут соединиться напрямую (NAT мобильного оператора).
# Запуск: bash /opt/nuvora/deploy/set-calls.sh   (update.sh запускает его сам, если ретранслятор ещё не настроен)
set -euo pipefail
APP_DIR=/opt/nuvora
ENV="$APP_DIR/.env"
[ -f "$ENV" ] || { echo "Нет $ENV — сначала установите Nuvora"; exit 1; }

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

echo "==> Устанавливаю coturn"
command -v turnserver >/dev/null || { apt-get update -qq; DEBIAN_FRONTEND=noninteractive apt-get install -y -qq coturn >/dev/null; }

SECRET=$(grep -E '^TURN_SECRET=' "$ENV" | cut -d= -f2- || true)
[ -n "$SECRET" ] || SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))")
SITE=$(grep -E '^SITE_URL=' "$ENV" | cut -d= -f2- | sed -E 's#^https?://##; s#/.*$##; s#:.*$##')
REALM=${SITE:-nuvora}
IP=$(curl -4 -s --max-time 5 https://api.ipify.org || true)

cat > /etc/turnserver.conf <<CONF
# Nuvora: ретранслятор для звонков. Пароли временные (выдаёт сайт), общий секрет — TURN_SECRET в $ENV
listening-port=3478
fingerprint
use-auth-secret
static-auth-secret=$SECRET
realm=$REALM
${IP:+external-ip=$IP}
min-port=49160
max-port=49200
total-quota=60
user-quota=4
stale-nonce=600
no-multicast-peers
no-cli
no-tlsv1
no-tlsv1_1
# не пускать трафик во внутренние сети сервера
denied-peer-ip=0.0.0.0-0.255.255.255
denied-peer-ip=10.0.0.0-10.255.255.255
denied-peer-ip=100.64.0.0-100.127.255.255
denied-peer-ip=127.0.0.0-127.255.255.255
denied-peer-ip=169.254.0.0-169.254.255.255
denied-peer-ip=172.16.0.0-172.31.255.255
denied-peer-ip=192.168.0.0-192.168.255.255
denied-peer-ip=::1
denied-peer-ip=fc00::-fdff:ffff:ffff:ffff:ffff:ffff:ffff:ffff
denied-peer-ip=fe80::-febf:ffff:ffff:ffff:ffff:ffff:ffff:ffff
log-file=syslog
simple-log
CONF
[ -f /etc/default/coturn ] && sed -i 's/^#\?TURNSERVER_ENABLED=.*/TURNSERVER_ENABLED=1/' /etc/default/coturn
systemctl enable -q coturn
systemctl restart coturn

if command -v ufw >/dev/null && ufw status | grep -q active; then
  ufw allow 3478 >/dev/null
  ufw allow 49160:49200/udp >/dev/null
fi

set_var TURN_SECRET "$SECRET"
chown nuvora:nuvora "$ENV"; chmod 600 "$ENV"
systemctl restart nuvora
echo "Готово: ретранслятор звонков работает на порту 3478${IP:+ ($IP)}."
echo "Если у хостинга есть свой файрвол в панели — откройте там 3478 (TCP и UDP) и 49160–49200 (UDP)."
