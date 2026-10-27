#!/usr/bin/env bash
# Переезд Nuvora на новый сервер. Запускать на СТАРОМ сервере:
#   bash /opt/nuvora/deploy/migrate.sh <IP-нового-сервера>
# Пароль root нового сервера спросят один раз. Копируются база, загрузки, .env (SECRET_KEY!), школа и HTTPS-сертификаты.
# Сайт недоступен несколько минут (пока копируется база), потом работает на новом сервере,
# как только A-записи домена указывают на новый IP.
set -euo pipefail
NEW="${1:?Укажите IP нового сервера: bash deploy/migrate.sh 1.2.3.4}"
APP_DIR=/opt/nuvora
BRANCH=$(git -C "$APP_DIR" rev-parse --abbrev-ref HEAD)
REPO="https://github.com/ildarchikiziandk-ui/quant.git"
DOMAIN=$(grep -E '^SITE_URL=' "$APP_DIR/.env" | cut -d= -f2- | sed -E 's#^https?://##; s#/.*$##; s#:.*$##')
[ -n "$DOMAIN" ] || { echo "Не нашёл SITE_URL в $APP_DIR/.env"; exit 1; }
if grep -qE '^DATABASE_URL=postgres' "$APP_DIR/.env"; then
  echo "База в PostgreSQL — этот скрипт переносит только SQLite. Напишите, сделаем по-другому."; exit 1
fi
SSH="ssh -o StrictHostKeyChecking=accept-new root@$NEW"

echo "==> 1/6 Ключ для входа на $NEW (спросит пароль root нового сервера один раз)"
[ -f ~/.ssh/id_ed25519 ] || ssh-keygen -q -t ed25519 -N "" -f ~/.ssh/id_ed25519
ssh-copy-id -o StrictHostKeyChecking=accept-new -i ~/.ssh/id_ed25519.pub "root@$NEW" >/dev/null
$SSH true

echo "==> 2/6 Код на новом сервере (ветка $BRANCH)"
command -v rsync >/dev/null || apt-get install -y -qq rsync >/dev/null
$SSH "export DEBIAN_FRONTEND=noninteractive; apt-get update -qq && apt-get install -y -qq git rsync >/dev/null
      [ -d $APP_DIR/.git ] || git clone -q -b $BRANCH $REPO $APP_DIR"

COPY=(.env uploads)
[ -d "$APP_DIR/school/data" ] && COPY+=(school/data school/.env)

echo "==> 3/6 Предварительное копирование загрузок (сайт пока работает)"
rsync -aR --info=stats1 -e "ssh -o StrictHostKeyChecking=accept-new" "$APP_DIR/./uploads" "root@$NEW:$APP_DIR/"

echo "==> 4/6 Останавливаю сайт и копирую базу и всё остальное"
systemctl stop nuvora
systemctl stop nuvora-school 2>/dev/null || true
# если дальше что-то сломается — старый сайт снова включится, ничего не потеряно
trap 'echo "Ошибка — включаю сайт обратно на старом сервере"; systemctl start nuvora; systemctl start nuvora-school 2>/dev/null || true' ERR
cd "$APP_DIR"
rsync -aR --delete --info=stats1 -e "ssh -o StrictHostKeyChecking=accept-new" "${COPY[@]}" quant.db* "root@$NEW:$APP_DIR/"
[ -d /etc/letsencrypt/live ] && rsync -a -e "ssh -o StrictHostKeyChecking=accept-new" /etc/letsencrypt/ "root@$NEW:/etc/letsencrypt/"
echo "==> 5/6 Установка на новом сервере"
$SSH "BRANCH=$BRANCH bash $APP_DIR/deploy/install.sh $DOMAIN && bash $APP_DIR/deploy/set-calls.sh"
if [ -d "$APP_DIR/school/data" ]; then
  SCHOOL=$(grep -E '^SCHOOL_SITE_URL=' "$APP_DIR/school/.env" | cut -d= -f2- | sed -E 's#^https?://##; s#/.*$##')
  $SSH "bash $APP_DIR/deploy/school.sh ${SCHOOL:-school.$DOMAIN}" || echo "Школа не настроилась — повторите на новом сервере: bash $APP_DIR/deploy/school.sh"
fi

echo "==> 6/6 Проверка"
$SSH "systemctl is-active nuvora && curl -fsS -o /dev/null -w 'сайт отвечает: %{http_code}\n' -H 'Host: $DOMAIN' http://127.0.0.1:8000/"

trap - ERR
# старый сервер больше не должен принимать записи — иначе новые посты потеряются
systemctl disable -q nuvora 2>/dev/null || true
systemctl disable -q nuvora-school 2>/dev/null || true

echo
echo "Готово. Осталось в DNS домена $DOMAIN поменять A-записи на $NEW:"
echo "  @ (сам $DOMAIN), www и school (если есть)."
echo "Старый сервер остановлен. Удаляйте его через несколько дней, когда убедитесь, что всё на месте."
