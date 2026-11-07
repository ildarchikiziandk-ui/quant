#!/usr/bin/env bash
# Встроенная озвучка постов (7.11.2026): программа Piper (рисует голос прямо на сервере, без чужих сервисов)
# и русские голоса Ирина, Денис, Дмитрий, Руслан. Какой звучит на сайте — выбирается в админке → «Озвучка».
# Запуск: bash /opt/nuvora/deploy/set-tts.sh
set -uo pipefail
export DEBIAN_FRONTEND=noninteractive NEEDRESTART_MODE=l NEEDRESTART_SUSPEND=1
APP_DIR=/opt/nuvora
DIR="$APP_DIR/data/tts/voices"
BASE="https://huggingface.co/rhasspy/piper-voices/resolve/main/ru/ru_RU"
mkdir -p "$DIR"

echo "==> 1/3 Программы"
apt-get install -y -qq ffmpeg >/dev/null 2>&1 || (apt-get update -qq >/dev/null 2>&1 && apt-get install -y -qq ffmpeg >/dev/null 2>&1) || echo "   ffmpeg не встал — озвучка будет в wav (файлы крупнее)"
"$APP_DIR/venv/bin/pip" install -q "piper-tts==1.8.0" || { echo "Не удалось установить Piper — пришлите этот вывод Claude"; exit 1; }

echo "==> 2/3 Голоса (по ~60 МБ)"
for V in irina denis dmitri ruslan; do
  F="ru_RU-$V-medium"
  if [ -s "$DIR/$F.onnx" ] && [ -s "$DIR/$F.onnx.json" ]; then echo "   $V — уже есть"; continue; fi
  if curl -fsSL --retry 3 -o "$DIR/$F.onnx.part" "$BASE/$V/medium/$F.onnx?download=true" \
     && curl -fsSL --retry 3 -o "$DIR/$F.onnx.json" "$BASE/$V/medium/$F.onnx.json?download=true"; then
    mv "$DIR/$F.onnx.part" "$DIR/$F.onnx"
    curl -fsSL --retry 3 -o "$DIR/$F.MODEL_CARD" "$BASE/$V/medium/MODEL_CARD?download=true" || true
    echo "   $V — готово"
  else
    rm -f "$DIR/$F.onnx.part" "$DIR/$F.onnx.json"; echo "   $V — не скачался (пропускаю)"
  fi
done
chown -R nuvora:nuvora "$APP_DIR/data/tts" 2>/dev/null || true

echo "==> 3/3 Проверка"
cd "$APP_DIR" && sudo -u nuvora env $(grep -v '^#' "$APP_DIR/.env" | xargs) "$APP_DIR/venv/bin/python" - <<'PY'
from services import tts
vs = tts.voices()
if not vs:
    raise SystemExit("Голосов нет — пришлите этот вывод Claude")
for vid, name, lic in vs:
    print(f"   {name}: лицензия — {lic}{'  (только некоммерческое — на сайте лучше не ставить)' if tts.noncommercial(vid) else ''}")
p, mt = tts.speak("Проверка озвучки. Всё работает!", vs[0][0])
print("   пример записан:", p)
PY
systemctl restart nuvora
echo "Готово. Выберите голос: админка → «Озвучка» (nvurl.ru/admin/tts), там же — «Студия голоса», чтобы записать свой."
