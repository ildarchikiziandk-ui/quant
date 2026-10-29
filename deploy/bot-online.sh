#!/usr/bin/env bash
# claude_ai в сети с самого сервера: лайки, ответы в личке, крестики-нолики, заранее написанные посты.
# Запуск: bash /opt/nuvora/deploy/bot-online.sh [минуты, по умолчанию 60]   Журнал: tail -f /opt/nuvora/bot.log
# Остановить раньше: bash /opt/nuvora/deploy/bot-online.sh stop
set -euo pipefail
APP_DIR=/opt/nuvora
if [ "${1:-}" = stop ]; then
  pkill -f "^$APP_DIR/venv/bin/python $APP_DIR/tools/bot_online.py" && echo "Остановлен." || echo "Не был запущен."
  exit 0
fi
MIN="${1:-60}"
read -rsp "Пароль аккаунта claude_ai (символы не видны): " PW; echo
pkill -f "^$APP_DIR/venv/bin/python $APP_DIR/tools/bot_online.py" 2>/dev/null || true
cd "$APP_DIR"
NUVORA_BOT_PASSWORD="$PW" nohup "$APP_DIR/venv/bin/python" "$APP_DIR/tools/bot_online.py" "$MIN" > "$APP_DIR/bot.log" 2>&1 &
sleep 4
cat "$APP_DIR/bot.log"
echo
echo "Работает в фоне $MIN мин — окно можно закрыть. Смотреть, что делает: tail -f $APP_DIR/bot.log (выход — Ctrl+C)"
