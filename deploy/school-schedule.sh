#!/usr/bin/env bash
# Вставить в школу расписание занятий (из school/manage.py, SISTER_PLAN). Текущее расписание заменяется.
# Запуск: bash /opt/nuvora/deploy/school-schedule.sh 10:00     (время начала первого урока)
set -euo pipefail
APP_DIR=/opt/nuvora
START="${1:-10:00}"
cd "$APP_DIR" && sudo -u nuvora env $(grep -v '^#' "$APP_DIR/school/.env" | xargs) "$APP_DIR/venv/bin/python" -m school.manage schedule --start "$START"
