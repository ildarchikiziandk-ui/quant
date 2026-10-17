#!/usr/bin/env bash
# Данные оператора персональных данных (152-ФЗ) — попадают в /privacy и /consent.
# Запуск: bash /opt/nuvora/deploy/set-operator.sh
set -euo pipefail
ENV=/opt/nuvora/.env
echo "Данные увидят пользователи в политике конфиденциальности. Домашний адрес писать не нужно — достаточно города."
read -rp "ФИО полностью: " NAME
read -rp "ИНН (12 цифр): " INN
read -rp "Город (например, Новосибирск): " CITY
read -rp "Почта для обращений по персональным данным: " MAIL
read -rp "Где сервер (например, «Россия, Москва, VK Cloud»): " WHERE
set_var() {
  python3 - "$ENV" "$1" "$2" <<'PY'
import sys
path, key, val = sys.argv[1:]
lines = open(path, encoding="utf-8").read().splitlines()
if any(l.startswith(key + "=") for l in lines):
    lines = [f"{key}={val}" if l.startswith(key + "=") else l for l in lines]
else:
    lines.append(f"{key}={val}")
open(path, "w", encoding="utf-8").write("\n".join(lines) + "\n")
PY
}
set_var OPERATOR_NAME "$NAME"
set_var OPERATOR_INN "$INN"
set_var OPERATOR_ADDRESS "г. $CITY"
set_var OPERATOR_EMAIL "$MAIL"
set_var SERVER_LOCATION "$WHERE"
chown nuvora:nuvora "$ENV" 2>/dev/null || true; chmod 600 "$ENV"
systemctl restart nuvora
echo "Готово. Проверьте страницу https://nvra.ru/privacy и вкладку «Закон» в админ-панели."
