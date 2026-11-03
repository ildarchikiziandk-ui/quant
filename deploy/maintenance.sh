#!/usr/bin/env bash
# Технические работы: сайт видят только владелец и модераторы, остальным — заглушка с текстом.
#   bash /opt/nuvora/deploy/maintenance.sh on "Нувора переезжает на новый сервер. Скоро вернёмся!"
#   bash /opt/nuvora/deploy/maintenance.sh off
set -euo pipefail
APP_DIR=/opt/nuvora
MODE="${1:?Укажите on или off}"
TEXT="${2:-Nuvora переезжает на новый сервер и восстанавливает данные. Скоро вернёмся!}"
cd "$APP_DIR"
sudo -u nuvora env MODE="$MODE" TEXT="$TEXT" "$APP_DIR/venv/bin/python" - <<'PY'
import os
from database import Base, engine, SessionLocal
import models  # noqa: F401  таблицы сайта
from packs.v3 import models as m  # noqa: F401
from packs.v3 import site
Base.metadata.create_all(engine)
db = SessionLocal()
on = os.environ["MODE"] == "on"
site.put(db, "maintenance", on)
if on:
    site.put(db, "maintenance_text", os.environ["TEXT"])
db.close()
print("Технические работы ВКЛЮЧЕНЫ" if on else "Технические работы выключены — сайт открыт для всех")
PY
