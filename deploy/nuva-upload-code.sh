#!/usr/bin/env bash
# Код для загрузки дообученной модели Нувы из Google Colab на этот сервер.
# Запуск: bash /opt/nuvora/deploy/nuva-upload-code.sh   — покажет код; вставьте его в блокнот Colab.
set -euo pipefail
APP_DIR=/opt/nuvora
ENV="$APP_DIR/.env"
CODE=$(python3 -c "import secrets; print(secrets.token_urlsafe(24))")
python3 - "$ENV" "$CODE" <<'PY'
import sys
path, code = sys.argv[1:]
lines = [l for l in open(path, encoding="utf-8").read().splitlines() if not l.startswith("NUVA_UPLOAD_CODE=")]
lines.append(f"NUVA_UPLOAD_CODE={code}")
open(path, "w", encoding="utf-8").write("\n".join(lines) + "\n")
PY
mkdir -p "$APP_DIR/data/ai" && chown -R nuvora:nuvora "$APP_DIR/data"
systemctl restart nuvora
echo
echo "Код загрузки (вставьте его в блокнот Colab, в поле CODE):"
echo
echo "    $CODE"
echo
echo "Когда блокнот напишет «Модель загружена», запустите: bash $APP_DIR/deploy/set-local-ai.sh"
