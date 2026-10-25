#!/usr/bin/env bash
# Школа (электронный дневник) на поддомене: отдельная служба, своя база, свой HTTPS-сертификат.
# Сначала в DNS добавьте A-запись: school → IP этого сервера (как у nvra.ru).
# Запуск:  sudo bash /opt/nuvora/deploy/school.sh            (домен school.nvra.ru, логин учителя rubl)
#          sudo bash /opt/nuvora/deploy/school.sh school.nvra.ru rubl
# Повторный запуск безопасен: база и пароли сохраняются; пароль учителя можно сменить командой из конца вывода.
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive NEEDRESTART_MODE=l NEEDRESTART_SUSPEND=1
DOMAIN="${1:-school.nvra.ru}"
LOGIN="${2:-rubl}"
APP_DIR=/opt/nuvora
DIR="$APP_DIR/school"
ENV="$DIR/.env"
PY="$APP_DIR/venv/bin/python"
[ -x "$PY" ] || { echo "Сначала установите Nuvora (deploy/install.sh) — школа живёт на том же сервере"; exit 1; }

echo "==> 1/5 Настройки школы ($ENV)"
mkdir -p "$DIR/data"
if [ ! -f "$ENV" ]; then
  SECRET=$(python3 -c "import secrets; print(secrets.token_urlsafe(48))")
  cat > "$ENV" <<EOS
SCHOOL_SECRET_KEY=$SECRET
SCHOOL_SITE_URL=https://$DOMAIN
SCHOOL_COOKIE_SECURE=1
SCHOOL_TEACHER_LOGIN=$LOGIN
SCHOOL_DATABASE_URL=sqlite:///$DIR/data/school.db
EOS
fi
chown -R nuvora:nuvora "$DIR"
chmod 600 "$ENV"

echo "==> 2/5 Служба nuvora-school (порт 8010)"
cat > /etc/systemd/system/nuvora-school.service <<EOS
[Unit]
Description=School diary (school.nvra.ru)
After=network.target

[Service]
User=nuvora
WorkingDirectory=$APP_DIR
EnvironmentFile=$ENV
ExecStart=$APP_DIR/venv/bin/uvicorn school.app:app --host 127.0.0.1 --port 8010 --proxy-headers --forwarded-allow-ips=127.0.0.1
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOS
systemctl daemon-reload
systemctl enable -q --now nuvora-school
systemctl restart nuvora-school

echo "==> 3/5 Кабинет учителя"
if sudo -u nuvora env $(grep -v '^#' "$ENV" | xargs) "$PY" -c "
import sys; sys.path.insert(0, '$APP_DIR')
from school import db as m; m.init(); s = m.SessionLocal()
sys.exit(0 if s.query(m.User).filter_by(role='teacher').first() else 1)"; then
  echo "   учитель уже есть — пароль не трогаю"
else
  echo "   Придумайте пароль для входа учителя «$LOGIN» (буквы на экране не появляются):"
  cd "$APP_DIR" && sudo -u nuvora env $(grep -v '^#' "$ENV" | xargs) "$PY" -m school.manage teacher --login "$LOGIN"
fi

echo "==> 4/5 nginx для $DOMAIN"
cat > /etc/nginx/sites-available/nuvora-school <<EOS
server {
    listen 80;
    listen [::]:80;
    server_name $DOMAIN;
    client_max_body_size 5m;
    location / {
        proxy_pass http://127.0.0.1:8010;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
EOS
ln -sf /etc/nginx/sites-available/nuvora-school /etc/nginx/sites-enabled/nuvora-school
nginx -t
systemctl reload nginx

echo "==> 5/5 HTTPS-сертификат"
MY_IP=$(curl -fsS https://api.ipify.org || true)
DNS_IP=$(getent ahostsv4 "$DOMAIN" | awk 'NR==1{print $1}' || true)
if [ -n "$MY_IP" ] && [ "$MY_IP" != "$DNS_IP" ]; then
  echo "   ВНИМАНИЕ: $DOMAIN указывает на ${DNS_IP:-ничего}, а IP сервера — $MY_IP."
  echo "   Добавьте в DNS A-запись «school» → $MY_IP, подождите 5–30 минут и запустите этот скрипт ещё раз."
  exit 0
fi
certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos --register-unsafely-without-email --redirect

echo
echo "Готово! Откройте https://$DOMAIN/login — логин «$LOGIN»."
echo "Сменить пароль учителя:  cd $APP_DIR && sudo -u nuvora env \$(cat $ENV | xargs) $PY -m school.manage teacher --login $LOGIN"
echo "Логи школы:              journalctl -u nuvora-school -f"
