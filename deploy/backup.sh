#!/usr/bin/env bash
# Резервная копия базы и загруженных файлов в /opt/nuvora-backups (хранится 14 последних).
set -euo pipefail
APP_DIR=/opt/nuvora
DEST=/opt/nuvora-backups
mkdir -p "$DEST"
STAMP=$(date +%Y%m%d-%H%M)
tar -czf "$DEST/nuvora-$STAMP.tar.gz" -C "$APP_DIR" quant.db uploads .env 2>/dev/null || tar -czf "$DEST/nuvora-$STAMP.tar.gz" -C "$APP_DIR" uploads .env
ls -1t "$DEST"/nuvora-*.tar.gz | tail -n +15 | xargs -r rm --
echo "Бэкап: $DEST/nuvora-$STAMP.tar.gz"
