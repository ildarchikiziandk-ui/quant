#!/usr/bin/env bash
# Справочник всех населённых пунктов мира для поля «Город» (GeoNames). Скачивает ~600 МБ, собирает 10–30 минут.
# Запуск: bash /opt/nuvora/deploy/places.sh        (в фоне: bash /opt/nuvora/deploy/places.sh bg)
set -euo pipefail
APP_DIR=/opt/nuvora
LOG="$APP_DIR/places.log"
if [ "${1:-}" = "bg" ]; then
  nohup flock -n /tmp/nuvora-places.lock "$APP_DIR/venv/bin/python" "$APP_DIR/tools/build_places.py" >"$LOG" 2>&1 &
  echo "Справочник городов собирается в фоне (10–30 минут). Ход: tail -f $LOG"
  exit 0
fi
flock -n /tmp/nuvora-places.lock "$APP_DIR/venv/bin/python" "$APP_DIR/tools/build_places.py"
chown nuvora:nuvora "$APP_DIR/places.sqlite"
echo "Готово: теперь город выбирается из списка."
