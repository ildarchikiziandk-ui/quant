#!/usr/bin/env bash
# Восстановление Нуворы из копии, скачанной в админке («Копия сайта»).
# Запуск на новом сервере ПОСЛЕ deploy/install.sh:
#   bash /opt/nuvora/deploy/restore.sh /root/nuvora-baza-....zip [/root/nuvora-foto-....tar.gz]
set -euo pipefail
APP_DIR=/opt/nuvora
DB_ZIP="${1:?Укажите архив с базой: bash restore.sh nuvora-baza-....zip [nuvora-foto-....tar.gz]}"
FILES="${2:-}"
command -v unzip >/dev/null || apt-get install -y unzip >/dev/null
TMP=$(mktemp -d)
unzip -q "$DB_ZIP" -d "$TMP"
systemctl stop nuvora nuvora-school 2>/dev/null || true
[ -f "$APP_DIR/quant.db" ] && cp "$APP_DIR/quant.db" "$APP_DIR/quant.db.before-restore"
cp "$TMP/quant.db" "$APP_DIR/quant.db"
rm -f "$APP_DIR/quant.db-wal" "$APP_DIR/quant.db-shm"
[ -f "$TMP/env.txt" ] && cp "$TMP/env.txt" "$APP_DIR/.env"
if [ -f "$TMP/school.db" ]; then mkdir -p "$APP_DIR/school/data"; cp "$TMP/school.db" "$APP_DIR/school/data/school.db"; fi
if [ -n "$FILES" ]; then mkdir -p "$APP_DIR/uploads"; tar -xzf "$FILES" -C "$APP_DIR/uploads"; fi
chown -R nuvora:nuvora "$APP_DIR"
rm -rf "$TMP"
systemctl start nuvora
systemctl start nuvora-school 2>/dev/null || true
echo "Готово! Нувора восстановлена из копии. Проверьте сайт в браузере."
