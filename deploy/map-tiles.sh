#!/usr/bin/env bash
# Картинки-плитки для «Nuvora Карты» (/map). Рисуются один раз (≈10–15 минут), потом карта не перерисовывается при приближении.
# Запуск: bash /opt/nuvora/deploy/map-tiles.sh      (в фоне: bash /opt/nuvora/deploy/map-tiles.sh bg)
set -euo pipefail
APP_DIR=/opt/nuvora
LOG="$APP_DIR/map-tiles.log"
RUN=(nice -n 15 flock -n /tmp/nuvora-tiles.lock "$APP_DIR/venv/bin/python" "$APP_DIR/tools/render_vt_tiles.py" --if-needed)
if [ "${1:-}" = "bg" ]; then
  nohup "${RUN[@]}" >"$LOG" 2>&1 &
  echo "Карта рисуется в фоне (10–15 минут). Ход: tail -f $LOG"
  exit 0
fi
"${RUN[@]}"
chown -R nuvora:nuvora "$APP_DIR/static/packs/v3/map/tiles"
echo "Готово: карта теперь из готовых картинок."
