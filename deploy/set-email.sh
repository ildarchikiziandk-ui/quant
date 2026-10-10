#!/usr/bin/env bash
# Настройка отправки писем (подтверждение email, сброс пароля). Запуск: bash /opt/nuvora/deploy/set-email.sh
set -euo pipefail
APP_DIR=/opt/nuvora
ENV="$APP_DIR/.env"

echo "С какой почты сайт будет отправлять письма?"
echo "  1) Mail.ru (а также @inbox.ru, @list.ru, @bk.ru, @internet.ru)"
echo "  2) Яндекс (@yandex.ru, @ya.ru)"
echo "  3) Другая (введу SMTP-сервер сам)"
read -rp "Номер [1]: " CHOICE
CHOICE=${CHOICE:-1}
case "$CHOICE" in
  1) HOST=smtp.mail.ru; PORT=465 ;;
  2) HOST=smtp.yandex.ru; PORT=465 ;;
  *) read -rp "SMTP-сервер: " HOST; read -rp "Порт [465]: " PORT; PORT=${PORT:-465} ;;
esac
read -rp "Адрес почты (например, nuvora@mail.ru): " USER_EMAIL
echo "Пароль ПРИЛОЖЕНИЯ (не обычный пароль от почты!). Символы при вводе не видны."
read -rsp "Пароль приложения: " PASS; echo

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
set_var SMTP_HOST "$HOST"
set_var SMTP_PORT "$PORT"
set_var SMTP_USER "$USER_EMAIL"
set_var SMTP_PASSWORD "$PASS"
set_var BRAND_EMAIL "$USER_EMAIL"
chown nuvora:nuvora "$ENV"; chmod 600 "$ENV"

echo "==> Отправляю тестовое письмо на $USER_EMAIL ..."
cd "$APP_DIR"
RESULT=$(sudo -u nuvora "$APP_DIR/venv/bin/python" -c "
import config
from services import mailer
err = mailer._send_sync(config.SMTP_USER, 'Проверка почты — ' + config.BRAND_NAME, mailer._wrap('Почта работает ✅', '<p>Письма с сайта теперь отправляются.</p>'))
print('OK' if err is None else 'ERR ' + err)
" 2>/dev/null | tail -1)
if [[ "$RESULT" == OK ]]; then
  systemctl restart nuvora
  echo "✅ Готово! Тестовое письмо отправлено, сайт перезапущен. Подтверждение email и восстановление пароля работают."
else
  echo "❌ Не получилось отправить письмо: ${RESULT#ERR }"
  echo "Чаще всего причина — нужен именно «пароль для внешних приложений», а не обычный пароль от почты."
  echo "Запустите скрипт ещё раз после исправления."
  exit 1
fi
