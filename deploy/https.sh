#!/usr/bin/env bash
# HTTPS для Nuvora через nginx + Let's Encrypt (certbot). Работает с российских серверов.
# Использование:  bash /opt/nuvora/deploy/https.sh nvra.ru
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive NEEDRESTART_MODE=a
DOMAIN="${1:?Укажите домен, например: nvra.ru}"

# убрать репозиторий Caddy, если он остался от прошлой попытки (иначе apt update ругается)
rm -f /etc/apt/sources.list.d/caddy-stable.list /usr/share/keyrings/caddy-stable-archive-keyring.gpg
systemctl disable --now caddy >/dev/null 2>&1 || true

echo "==> Ставлю nginx и certbot"
apt-get update -qq
apt-get install -y -qq nginx certbot python3-certbot-nginx >/dev/null

NAMES="$DOMAIN"
CERT_ARGS="-d $DOMAIN"
if [[ "$DOMAIN" != *.duckdns.org ]] && getent ahostsv4 "www.$DOMAIN" >/dev/null; then
  NAMES="$DOMAIN www.$DOMAIN"
  CERT_ARGS="$CERT_ARGS -d www.$DOMAIN"
fi

echo "==> Настраиваю nginx для: $NAMES"
cat > /etc/nginx/sites-available/nuvora <<EOS
server {
    listen 80;
    listen [::]:80;
    server_name $NAMES;
    client_max_body_size 110m;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 120s;
    }
}
EOS
ln -sf /etc/nginx/sites-available/nuvora /etc/nginx/sites-enabled/nuvora
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl enable -q nginx
systemctl restart nginx

if command -v ufw >/dev/null && ufw status | grep -q active; then ufw allow 'Nginx Full' >/dev/null; fi

echo "==> Получаю HTTPS-сертификат Let's Encrypt"
certbot --nginx $CERT_ARGS --non-interactive --agree-tos --register-unsafely-without-email --redirect

echo
echo "Готово! Откройте https://$DOMAIN"
