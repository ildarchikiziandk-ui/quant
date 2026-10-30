#!/usr/bin/env bash
# Короткие ссылки: nvurl.ru/123 → пост, nvurl.ru/@ник → профиль.
# Сначала в Рег.ру для домена добавьте A-записи «@» и «www» → IP этого сервера, подождите 15–60 минут.
# Запуск: bash /opt/nuvora/deploy/set-shortlinks.sh nvurl.ru
set -euo pipefail
APP_DIR=/opt/nuvora
DOMAIN="${1:-nvurl.ru}"
MYIP=$(curl -4 -s --max-time 10 https://ifconfig.me || hostname -I | awk '{print $1}')
GOT=$(getent ahostsv4 "$DOMAIN" | awk '{print $1; exit}' || true)
if [ "$GOT" != "$MYIP" ]; then
  echo "Домен $DOMAIN пока ведёт на «${GOT:-никуда}», а нужно на $MYIP."
  echo "Проверьте A-запись «@» в Рег.ру и подождите 15–60 минут, потом запустите команду снова."
  exit 1
fi
NAMES="$DOMAIN"; CERT="-d $DOMAIN"
if [ "$(getent ahostsv4 "www.$DOMAIN" | awk '{print $1; exit}' || true)" = "$MYIP" ]; then NAMES="$DOMAIN www.$DOMAIN"; CERT="$CERT -d www.$DOMAIN"; fi
cat > /etc/nginx/sites-available/nuvora-short <<EOS
server {
    listen 80;
    listen [::]:80;
    server_name $NAMES;
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
EOS
ln -sf /etc/nginx/sites-available/nuvora-short /etc/nginx/sites-enabled/nuvora-short
nginx -t && systemctl reload nginx
certbot --nginx $CERT --non-interactive --agree-tos --register-unsafely-without-email --redirect
# основной адрес сайта нужен, чтобы короткие ссылки вели на него, а не на localhost
SITE=$(grep -E '^SITE_URL=' "$APP_DIR/.env" | tail -1 | cut -d= -f2- | tr -d '"' || true)
if [ -z "$SITE" ] || [[ "$SITE" == *localhost* ]] || [[ "$SITE" == *127.0.0.1* ]]; then
  MAIN=$(awk '/server_name/{print $2; exit}' /etc/nginx/sites-available/nuvora 2>/dev/null | tr -d ';' || true)
  MAIN=${MAIN:-nvra.ru}
  sed -i '/^SITE_URL=/d' "$APP_DIR/.env"
  echo "SITE_URL=https://$MAIN" >> "$APP_DIR/.env"
  echo "Основной адрес сайта: https://$MAIN"
fi
sed -i '/^SHORT_DOMAIN=/d' "$APP_DIR/.env"
echo "SHORT_DOMAIN=$DOMAIN" >> "$APP_DIR/.env"
systemctl restart nuvora
echo
echo "Готово! Проверьте: https://$DOMAIN/@rubl — должен открыться ваш профиль на основном сайте."
