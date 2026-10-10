#!/usr/bin/env bash
# Установка Nuvora на чистый сервер Ubuntu 22.04/24.04 (или Debian 12).
# Использование:  sudo bash deploy/install.sh <поддомен-duckdns> <токен-duckdns> [ветка]
# Пример:         sudo bash deploy/install.sh quantru 1a2b3c4d-....
set -euo pipefail

SUB="${1:?Укажите поддомен DuckDNS, например: quantru}"
TOKEN="${2:?Укажите токен DuckDNS (на странице duckdns.org вверху)}"
BRANCH="${3:-claude/happy-wozniak-vvu5w4}"
DOMAIN="${SUB}.duckdns.org"
APP_DIR=/opt/nuvora
REPO="https://github.com/ildarchikiziandk-ui/quant.git"

echo "==> 1/6 Обновляю DuckDNS: ${DOMAIN} -> IP этого сервера"
mkdir -p /opt/duckdns
cat > /opt/duckdns/update.sh <<EOS
#!/bin/sh
curl -fsS "https://www.duckdns.org/update?domains=${SUB}&token=${TOKEN}&ip=" -o /opt/duckdns/last.log
EOS
chmod 700 /opt/duckdns/update.sh
/opt/duckdns/update.sh && echo "   ответ DuckDNS: $(cat /opt/duckdns/last.log)"
( crontab -l 2>/dev/null | grep -v duckdns/update.sh; echo "*/5 * * * * /opt/duckdns/update.sh >/dev/null 2>&1" ) | crontab -

echo "==> 2/6 Ставлю пакеты (python, git, caddy)"
apt-get update -qq
apt-get install -y -qq python3 python3-venv python3-pip git curl debian-keyring debian-archive-keyring apt-transport-https gnupg >/dev/null
if ! command -v caddy >/dev/null; then
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' > /etc/apt/sources.list.d/caddy-stable.list
  apt-get update -qq && apt-get install -y -qq caddy >/dev/null
fi

echo "==> 3/6 Код приложения в ${APP_DIR} (ветка ${BRANCH})"
id nuvora >/dev/null 2>&1 || useradd --system --home "${APP_DIR}" --shell /usr/sbin/nologin nuvora
if [ -d "${APP_DIR}/.git" ]; then
  git -C "${APP_DIR}" fetch -q origin "${BRANCH}" && git -C "${APP_DIR}" checkout -q "${BRANCH}" && git -C "${APP_DIR}" reset -q --hard "origin/${BRANCH}"
else
  git clone -q -b "${BRANCH}" "${REPO}" "${APP_DIR}"
fi
python3 -m venv "${APP_DIR}/venv"
"${APP_DIR}/venv/bin/pip" install -q --upgrade pip
"${APP_DIR}/venv/bin/pip" install -q -r "${APP_DIR}/requirements.txt"

echo "==> 4/6 Настройки (.env)"
if [ ! -f "${APP_DIR}/.env" ]; then
  cp "${APP_DIR}/.env.example" "${APP_DIR}/.env"
  SECRET=$(python3 -c "import secrets; print(secrets.token_urlsafe(48))")
  sed -i "s|^SECRET_KEY=.*|SECRET_KEY=${SECRET}|; s|^SITE_URL=.*|SITE_URL=https://${DOMAIN}|; s|^BRAND_EMAIL=.*|BRAND_EMAIL=support@${DOMAIN}|" "${APP_DIR}/.env"
  echo "   создан ${APP_DIR}/.env — допишите туда почту/push/Яндекс при необходимости"
fi
mkdir -p "${APP_DIR}/uploads"
chown -R nuvora:nuvora "${APP_DIR}"
chmod 600 "${APP_DIR}/.env"

echo "==> 5/6 Служба systemd"
cat > /etc/systemd/system/nuvora.service <<EOS
[Unit]
Description=Nuvora social network
After=network.target

[Service]
User=nuvora
WorkingDirectory=${APP_DIR}
ExecStart=${APP_DIR}/venv/bin/uvicorn main:app --host 127.0.0.1 --port 8000 --proxy-headers --forwarded-allow-ips=127.0.0.1
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOS
systemctl daemon-reload
systemctl enable -q --now nuvora
systemctl restart nuvora

echo "==> 6/6 HTTPS через Caddy (сертификат Let's Encrypt выпустится сам)"
cat > /etc/caddy/Caddyfile <<EOS
${DOMAIN} {
    encode gzip
    request_body {
        max_size 110MB
    }
    reverse_proxy 127.0.0.1:8000
}
EOS
systemctl enable -q caddy
systemctl reload caddy || systemctl restart caddy

if command -v ufw >/dev/null && ufw status | grep -q active; then ufw allow 80,443/tcp >/dev/null; fi

echo
echo "Готово! Откройте https://${DOMAIN}"
echo "Логи приложения:  journalctl -u nuvora -f"
echo "Обновление кода:  sudo bash ${APP_DIR}/deploy/update.sh"
