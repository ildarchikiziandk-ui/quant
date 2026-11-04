#!/usr/bin/env bash
# Вернуть старые данные (из копии Beget или «Копии сайта») и объединить с тем, что уже есть на новом сервере.
# Положите в одну папку файлы из старой копии: quant.db (и quant.db-wal, если есть), .env (или env.txt), папку uploads,
# school.db (и school.db-wal) — что есть. Файлы из бэкапа Beget снимались «на ходу»: скрипт сам вливает -wal и проверяет базы.
#   bash /opt/nuvora/deploy/merge.sh /root/old
# Старые аккаунты, посты и переписки возвращаются; новые люди и посты остаются. Если логин заняли дважды —
# новому человеку выдаётся временный логин userNNNN (входит он по-прежнему своим логином и паролем, на сайте видит плашку).
set -euo pipefail
APP_DIR=/opt/nuvora
OLD="${1:?Укажите папку со старыми файлами, например: bash merge.sh /root/old}"
OLD_ENV="$OLD/.env"; [ -f "$OLD_ENV" ] || OLD_ENV="$OLD/env.txt"
[ -f "$OLD/quant.db" ] || { echo "В папке $OLD нет quant.db"; exit 1; }
[ -f "$OLD_ENV" ] || { echo "В папке $OLD нет .env (или env.txt) — без старого ключа не откроются переписки"; exit 1; }
STAMP=$(date +%Y%m%d-%H%M)
echo "==> Проверяю старые базы (копия снималась с работающего сервера)"
command -v sqlite3 >/dev/null || DEBIAN_FRONTEND=noninteractive apt-get install -y -qq sqlite3 >/dev/null 2>&1 || true
"$APP_DIR/venv/bin/python" "$APP_DIR/tools/db_check.py" "$OLD/quant.db" || { echo "Старую базу открыть не удалось — пришлите этот вывод Claude"; exit 1; }
[ -f "$OLD/school.db" ] && { "$APP_DIR/venv/bin/python" "$APP_DIR/tools/db_check.py" "$OLD/school.db" || echo "База школы повреждена — школу оставляю как есть"; }
echo "==> Останавливаю сайт и сохраняю текущую базу (quant.db.before-merge-$STAMP)"
systemctl stop nuvora
cp "$APP_DIR/quant.db" "$APP_DIR/quant.db.before-merge-$STAMP"
cp "$APP_DIR/.env" "$APP_DIR/.env.before-merge-$STAMP"
echo "==> Объединяю базы"
cd "$APP_DIR"
"$APP_DIR/venv/bin/python" tools/merge_db.py "$OLD/quant.db" "$APP_DIR/quant.db.before-merge-$STAMP" /tmp/nuvora-merged.db "$OLD_ENV" "$APP_DIR/.env.before-merge-$STAMP" 2>&1 | grep -v "^\[migrations\]\|SECRET_KEY не задан"
mv /tmp/nuvora-merged.db "$APP_DIR/quant.db"
rm -f "$APP_DIR/quant.db-wal" "$APP_DIR/quant.db-shm"
echo "==> Возвращаю старый ключ шифрования (остальные настройки нового сервера не трогаю)"
for KEY in SECRET_KEY MESSAGE_KEY; do
  VAL=$(grep -E "^${KEY}=" "$OLD_ENV" | head -1 | cut -d= -f2- || true)
  sed -i "/^${KEY}=/d" "$APP_DIR/.env"
  [ -n "$VAL" ] && echo "${KEY}=${VAL}" >> "$APP_DIR/.env"
done
if [ -d "$OLD/uploads" ]; then echo "==> Возвращаю фото и файлы"; mkdir -p "$APP_DIR/uploads"; cp -rn "$OLD/uploads/." "$APP_DIR/uploads/"; fi
if [ -f "$OLD/school.db" ] && [ -d "$APP_DIR/school/data" ]; then
  echo "==> Возвращаю базу школы"
  systemctl stop nuvora-school 2>/dev/null || true
  [ -f "$APP_DIR/school/data/school.db" ] && cp "$APP_DIR/school/data/school.db" "$APP_DIR/school/data/school.db.before-merge-$STAMP"
  cp "$OLD/school.db" "$APP_DIR/school/data/school.db"
  systemctl start nuvora-school 2>/dev/null || true
fi
chown -R nuvora:nuvora "$APP_DIR"
chmod 600 "$APP_DIR/.env"
systemctl start nuvora
echo "Готово! Старые данные вернулись. Все выйдут из аккаунтов — войти можно своим логином и паролем."
echo "Если что-то не так, откатить: systemctl stop nuvora && cp $APP_DIR/quant.db.before-merge-$STAMP $APP_DIR/quant.db && cp $APP_DIR/.env.before-merge-$STAMP $APP_DIR/.env && systemctl start nuvora"
