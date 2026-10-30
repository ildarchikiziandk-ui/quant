#!/usr/bin/env bash
# Обновить Nuvora до последней версии ветки и перезапустить.
set -euo pipefail
APP_DIR=/opt/nuvora
git config --global --get-all safe.directory 2>/dev/null | grep -qx "$APP_DIR" || git config --global --add safe.directory "$APP_DIR"
bash "$APP_DIR/deploy/backup.sh" || echo "Бэкап не удался — продолжаю обновление"
BRANCH=$(git -C "$APP_DIR" rev-parse --abbrev-ref HEAD)
[ "$BRANCH" = "ildarrr" ] || [ "$BRANCH" = "main" ] || BRANCH=ildarrr  # ветка переименована
git -C "$APP_DIR" fetch -q origin "$BRANCH"
git -C "$APP_DIR" checkout -q -f -B "$BRANCH" "origin/$BRANCH"
"$APP_DIR/venv/bin/pip" install -q -r "$APP_DIR/requirements.txt"
chown -R nuvora:nuvora "$APP_DIR"
# ретранслятор для звонков: ставится один раз, при следующих обновлениях пропускается
if ! grep -q '^TURN_SECRET=.' "$APP_DIR/.env" 2>/dev/null; then
  bash "$APP_DIR/deploy/set-calls.sh" || echo "Ретранслятор звонков не установился — звонки будут работать напрямую. Повторить: bash $APP_DIR/deploy/set-calls.sh"
fi
systemctl restart nuvora
# справочник городов, сёл и деревень мира: собирается один раз, в фоне
[ -f "$APP_DIR/places.sqlite" ] || bash "$APP_DIR/deploy/places.sh" bg || true
# школа (school.nvra.ru), если установлена
if systemctl list-unit-files nuvora-school.service >/dev/null 2>&1 && [ -f "$APP_DIR/school/.env" ]; then
  chown -R nuvora:nuvora "$APP_DIR/school"
  systemctl restart nuvora-school
fi
echo "Обновлено до $(git -C "$APP_DIR" log --oneline -1)"
