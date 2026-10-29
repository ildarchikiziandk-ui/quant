#!/usr/bin/env bash
# Настройка отправки писем (подтверждение email, сброс пароля). Запуск: bash /opt/nuvora/deploy/set-email.sh
set -euo pipefail
APP_DIR=/opt/nuvora
ENV="$APP_DIR/.env"

echo "С какой почты сайт будет отправлять письма?"
echo "  1) Mail.ru (а также @inbox.ru, @list.ru, @bk.ru, @internet.ru)"
echo "  2) Яндекс (@yandex.ru, @ya.ru)"
echo "  3) Почта на своём домене в Beget (например, welcome@nvra.ru)"
echo "  4) Другая (введу SMTP-сервер сам)"
read -rp "Номер [1]: " CHOICE
CHOICE=${CHOICE:-1}
case "$CHOICE" in
  1) HOST=smtp.mail.ru; PORT=465 ;;
  2) HOST=smtp.yandex.ru; PORT=465 ;;
  3) HOST=smtp.beget.com; PORT=465 ;;
  *) read -rp "SMTP-сервер: " HOST; read -rp "Порт [465]: " PORT; PORT=${PORT:-465} ;;
esac
read -rp "Адрес почты (например, nuvora@mail.ru): " USER_EMAIL
if [ "$CHOICE" = 3 ]; then
  echo "Пароль от этого почтового ящика (тот, что задали в панели Beget). Символы при вводе не видны."
else
  echo "Пароль ПРИЛОЖЕНИЯ (не обычный пароль от почты!). Символы при вводе не видны."
fi
read -rsp "Пароль: " PASS; echo

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
set_var SMTP_USER "$USER_EMAIL"
set_var SMTP_PASSWORD "$PASS"
# ящик для вопросов отдельный: support@ домена; меняем только заглушку или адрес-отправитель
CUR=$(grep -E '^BRAND_EMAIL=' "$ENV" | cut -d= -f2- || true)
if [ -z "$CUR" ] || [[ "$CUR" == *example.* ]] || [ "$CUR" = "$USER_EMAIL" ]; then
  SITE=$(grep -E '^SITE_URL=' "$ENV" | cut -d= -f2- | sed -E 's#^https?://##; s#/.*$##; s#:.*$##' || true)
  [ -n "$SITE" ] && set_var BRAND_EMAIL "support@$SITE"
fi
chown nuvora:nuvora "$ENV"; chmod 600 "$ENV"

cd "$APP_DIR"
PORTS="$PORT"; [ "$PORT" = 465 ] && PORTS="465 587"; [ "$PORT" = 587 ] && PORTS="587 465"
[ "$HOST" = smtp.beget.com ] && PORTS="465 2525"  # у Beget запасной порт 2525
RESULT="ERR не проверено"
for P in $PORTS; do
  set_var SMTP_PORT "$P"
  chown nuvora:nuvora "$ENV"; chmod 600 "$ENV"
  echo "==> Пробую отправить тестовое письмо через $HOST:$P ..."
  RESULT=$(sudo -u nuvora "$APP_DIR/venv/bin/python" -c "
import config
from services import mailer
err = mailer._send_sync(config.SMTP_USER, 'Проверка почты — ' + config.BRAND_NAME, mailer._wrap('Почта работает ✅', '<p>Письма с сайта теперь отправляются.</p>'))
print('OK' if err is None else 'ERR ' + err)
" 2>/dev/null | tail -1)
  [[ "$RESULT" == OK ]] && break
  echo "   не вышло: ${RESULT#ERR }"
done

if [[ "$RESULT" == OK ]]; then
  systemctl restart nuvora
  echo "✅ Готово! Тестовое письмо отправлено на $USER_EMAIL, сайт перезапущен."
  echo "   Подтверждение email и восстановление пароля работают."
  if [ "$HOST" = smtp.beget.com ]; then
    echo "   Чтобы письма не попадали в спам, в DNS домена добавьте записи из панели Beget (Почта → DNS / SPF, DKIM)."
  fi
else
  echo
  echo "❌ Письмо отправить не удалось."
  echo "Ответ почтового сервера: ${RESULT#ERR }"
  case "$RESULT" in
    *535*|*uthentication*|*Invalid*|*password*|*Username*)
      if [ "$HOST" = smtp.beget.com ]; then
        echo "Beget отклонил пароль. Проверьте адрес ящика и пароль (в панели Beget: Почта → ящик → сменить пароль)."
      else
        echo "Почта отклонила пароль. Нужен «пароль для внешних приложений» из настроек почты,"
        echo "а не обычный пароль. Создайте его и запустите скрипт ещё раз."
      fi ;;
    *unreachable*|*timed\ out*|*Timeout*|*refused*|*101*|*110*|*111*)
      echo "Сервер не может подключиться к почтовому серверу — похоже, хостинг закрыл порты 465 и 587."
      echo "Напишите в поддержку хостинга: «Прошу открыть исходящие порты 465, 587 и 2525 (SMTP) на сервере $(curl -fsS https://api.ipify.org 2>/dev/null)»."
      echo "Когда откроют — запустите этот скрипт ещё раз." ;;
    *)
      echo "Ответ сервера: ${RESULT#ERR }" ;;
  esac
  exit 1
fi
