#!/usr/bin/env bash
# Резервная копия базы и загруженных файлов в /opt/nuvora-backups (хранится 14 последних).
set -euo pipefail
APP_DIR=/opt/nuvora
DEST=/opt/nuvora-backups
mkdir -p "$DEST"
STAMP=$(date +%Y%m%d-%H%M)
tar -czf "$DEST/nuvora-$STAMP.tar.gz" -C "$APP_DIR" quant.db uploads .env 2>/dev/null || tar -czf "$DEST/nuvora-$STAMP.tar.gz" -C "$APP_DIR" uploads .env
# школа: своя база и настройки
if [ -d "$APP_DIR/school/data" ]; then
  tar -czf "$DEST/school-$STAMP.tar.gz" -C "$APP_DIR/school" data .env 2>/dev/null || true
  ls -1t "$DEST"/school-*.tar.gz 2>/dev/null | tail -n +15 | xargs -r rm --
fi
ls -1t "$DEST"/nuvora-*.tar.gz | tail -n +15 | xargs -r rm --
echo "Бэкап: $DEST/nuvora-$STAMP.tar.gz"
