#!/usr/bin/env bash
# Обновить Nuvora до последней версии ветки и перезапустить.
set -euo pipefail
APP_DIR=/opt/nuvora
# без своего SECRET_KEY новая версия не запустится со старыми данными (запасного ключа от Quant больше нет) — не обновляем
if ! grep -q '^SECRET_KEY=.\{20,\}' "$APP_DIR/.env" 2>/dev/null; then
  echo "СТОП: в $APP_DIR/.env нет SECRET_KEY. Сайт не обновлён и работает как раньше. Пришлите этот вывод Claude, сам ключ не вписывайте."
  exit 1
fi
git config --global --get-all safe.directory 2>/dev/null | grep -qx "$APP_DIR" || git config --global --add safe.directory "$APP_DIR"
bash "$APP_DIR/deploy/backup.sh" || echo "Бэкап не удался — продолжаю обновление"
BRANCH=$(git -C "$APP_DIR" rev-parse --abbrev-ref HEAD)
[ "$BRANCH" = "ildarrr" ] || [ "$BRANCH" = "main" ] || BRANCH=ildarrr  # ветка переименована
git -C "$APP_DIR" fetch -q origin "$BRANCH"
git -C "$APP_DIR" checkout -q -f -B "$BRANCH" "origin/$BRANCH"
"$APP_DIR/venv/bin/pip" install -q -r "$APP_DIR/requirements.txt"
# старые библиотеки с неисправленными дырами (заменены на PyJWT 7.11.2026) — убираем
"$APP_DIR/venv/bin/pip" uninstall -y -q python-jose ecdsa >/dev/null 2>&1 || true
# защита (7.11.2026): файлы с ключами читает только сервер; nginx не называет свою версию
chmod 600 "$APP_DIR/.env" "$APP_DIR/school/.env" 2>/dev/null || true
if command -v nginx >/dev/null && [ ! -f /etc/nginx/conf.d/nuvora-hardening.conf ]; then
  echo "server_tokens off;" > /etc/nginx/conf.d/nuvora-hardening.conf
  if nginx -t >/dev/null 2>&1; then systemctl reload nginx || true; else rm -f /etc/nginx/conf.d/nuvora-hardening.conf; fi
fi
chown -R nuvora:nuvora "$APP_DIR"
# ретранслятор для звонков: ставится один раз, при следующих обновлениях пропускается
if ! grep -q '^TURN_SECRET=.' "$APP_DIR/.env" 2>/dev/null; then
  bash "$APP_DIR/deploy/set-calls.sh" || echo "Ретранслятор звонков не установился — звонки будут работать напрямую. Повторить: bash $APP_DIR/deploy/set-calls.sh"
fi
systemctl restart nuvora
# своя страница вместо «502 Bad Gateway», пока сайт перезапускается (один раз)
[ -f /etc/nginx/sites-available/nuvora ] && ! grep -q nuvora-502 /etc/nginx/sites-available/nuvora && bash "$APP_DIR/deploy/nginx-fix.sh" || true
# справочник городов, сёл и деревень мира: собирается один раз, в фоне
[ -f "$APP_DIR/places.sqlite" ] || bash "$APP_DIR/deploy/places.sh" bg || true
# карта Верх-Тулы удалена (4.11.2026): убираем её картинки, если остались
rm -rf "$APP_DIR/static/packs/v3/map" "$APP_DIR/map-tiles.log"
# школа (school.nvra.ru), если установлена
if systemctl list-unit-files nuvora-school.service >/dev/null 2>&1 && [ -f "$APP_DIR/school/.env" ]; then
  chown -R nuvora:nuvora "$APP_DIR/school"
  systemctl restart nuvora-school
fi
echo "Обновлено до $(git -C "$APP_DIR" log --oneline -1)"
