#!/usr/bin/env bash
# Своя нейросеть для Нувы прямо на этом сервере — без внешних сервисов и без отправки вопросов наружу.
# Ставит llama.cpp (программа, которая запускает нейросеть) и открытую модель Qwen2.5-Instruct (лицензия Apache 2.0),
# размер модели подбирается под память сервера. Служба nuvora-ai слушает только 127.0.0.1:8090.
# Запуск: bash /opt/nuvora/deploy/set-local-ai.sh        Выключить: bash /opt/nuvora/deploy/set-local-ai.sh off
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
APP_DIR=/opt/nuvora
ENV="$APP_DIR/.env"
DIR="$APP_DIR/data/ai"
PORT=8090

set_var() {
  python3 - "$ENV" "$1" "$2" <<'PY'
import sys
path, key, val = sys.argv[1:]
lines = open(path, encoding="utf-8").read().splitlines()
lines = [l for l in lines if not l.startswith(key + "=")]
if val:
    lines.append(f"{key}={val}")
open(path, "w", encoding="utf-8").write("\n".join(lines) + "\n")
PY
}

if [ "${1:-}" = "off" ]; then
  systemctl disable --now nuvora-ai 2>/dev/null || true
  set_var LOCAL_AI_URL ""
  systemctl restart nuvora
  echo "Своя нейросеть выключена. Нува снова отвечает по справке."
  exit 0
fi

MEM=$(free -m | awk '/^Mem:/{print $2}')
CPUS=$(nproc)
echo "==> Сервер: память ${MEM} МБ, ядер процессора: ${CPUS}"
if [ "$MEM" -lt 1800 ]; then
  echo "Памяти слишком мало для нейросети (нужно хотя бы 2 ГБ). В панели Beget можно увеличить тариф VPS."; exit 1
elif [ "$MEM" -lt 3500 ]; then
  REPO="Qwen/Qwen2.5-0.5B-Instruct-GGUF"; FILE="qwen2.5-0.5b-instruct-q4_k_m.gguf"; SIZE="маленькая (0,5 млрд параметров)"
  CTX=2048; LIMIT=700M
else
  REPO="Qwen/Qwen2.5-1.5B-Instruct-GGUF"; FILE="qwen2.5-1.5b-instruct-q4_k_m.gguf"; SIZE="средняя (1,5 млрд параметров)"
  CTX=4096; LIMIT=1600M
fi

# запасная память на диске (файл подкачки): если оперативной не хватит, сервер не упадёт, а просто чуть замедлится
if [ "$(swapon --show --noheadings | wc -l)" = "0" ]; then
  echo "==> Создаю файл подкачки 2 ГБ (запас памяти на диске)"
  fallocate -l 2G /swapfile 2>/dev/null || dd if=/dev/zero of=/swapfile bs=1M count=2048 status=none
  chmod 600 /swapfile && mkswap -q /swapfile && swapon /swapfile
  grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi
echo "    модель: $SIZE — $FILE"

mkdir -p "$DIR/bin"
apt-get install -y -qq unzip curl >/dev/null

echo "==> 1/3 Программа llama.cpp"
if [ ! -x "$DIR/bin/llama-server" ]; then
  # сначала пробуем готовую сборку с GitHub
  URL=$(curl -fsSL https://api.github.com/repos/ggml-org/llama.cpp/releases/latest 2>/dev/null | python3 -c "
import json,sys
try:
    for a in json.load(sys.stdin).get('assets', []):
        n=a['name']
        if 'bin-ubuntu-x64.' in n and (n.endswith('.zip') or n.endswith('.tar.gz')): print(a['browser_download_url']); break
except Exception:
    pass" 2>/dev/null || true)
  rm -rf /tmp/llama && mkdir -p /tmp/llama
  if [ -n "$URL" ] && curl -fL --progress-bar "$URL" -o /tmp/llama.pkg; then
    if [[ "$URL" == *.zip ]]; then unzip -q /tmp/llama.pkg -d /tmp/llama; else tar -xzf /tmp/llama.pkg -C /tmp/llama; fi
    SRV=$(find /tmp/llama -name llama-server -type f | head -1)
    [ -n "$SRV" ] && cp -a "$(dirname "$SRV")"/. "$DIR/bin/"
  fi
  # готовой сборки нет — собираем из исходного кода (10–20 минут, один раз)
  if [ ! -x "$DIR/bin/llama-server" ]; then
    echo "    готовой сборки нет — собираю из исходного кода, это займёт 10–20 минут, не закрывайте окно"
    apt-get install -y -qq build-essential cmake git libcurl4-openssl-dev >/dev/null
    JOBS=$([ "$MEM" -lt 3500 ] && echo 1 || echo "$CPUS")  # при малой памяти собираем в один поток, чтобы не упасть
    rm -rf /tmp/llama-src
    git clone -q --depth 1 https://github.com/ggml-org/llama.cpp /tmp/llama-src
    cmake -S /tmp/llama-src -B /tmp/llama-src/build -DCMAKE_BUILD_TYPE=Release -DBUILD_SHARED_LIBS=OFF -DLLAMA_CURL=OFF \
      -DLLAMA_BUILD_TESTS=OFF -DLLAMA_BUILD_EXAMPLES=OFF >/tmp/llama-cmake.log 2>&1 \
      || { echo "Не получилось подготовить сборку. Пришлите Claude: tail -20 /tmp/llama-cmake.log"; exit 1; }
    cmake --build /tmp/llama-src/build --config Release --target llama-server -j "$JOBS" >/tmp/llama-build.log 2>&1 \
      || { echo "Не получилось собрать. Пришлите Claude: tail -20 /tmp/llama-build.log"; exit 1; }
    cp /tmp/llama-src/build/bin/llama-server "$DIR/bin/"
    rm -rf /tmp/llama-src
  fi
  rm -rf /tmp/llama /tmp/llama.pkg
fi
[ -x "$DIR/bin/llama-server" ] || { echo "Программа llama.cpp не установилась — пришлите этот вывод Claude"; exit 1; }

echo "==> 2/3 Модель (скачивается один раз, 0,4–1,1 ГБ)"
if [ ! -s "$DIR/$FILE" ]; then
  curl -fL --progress-bar "https://huggingface.co/$REPO/resolve/main/$FILE" -o "$DIR/$FILE.part" \
    || curl -fL --progress-bar "https://hf-mirror.com/$REPO/resolve/main/$FILE" -o "$DIR/$FILE.part"
  mv "$DIR/$FILE.part" "$DIR/$FILE"
fi
chown -R nuvora:nuvora "$DIR"

echo "==> 3/3 Служба nuvora-ai"
cat > /etc/systemd/system/nuvora-ai.service <<EOS
[Unit]
Description=Nuva local AI (llama.cpp)
After=network.target

[Service]
User=nuvora
WorkingDirectory=$DIR
Environment=LD_LIBRARY_PATH=$DIR/bin
ExecStart=$DIR/bin/llama-server -m $DIR/$FILE --host 127.0.0.1 --port $PORT -c $CTX -t $CPUS --parallel 1 --alias nuva
Restart=always
Nice=10
# памяти не больше LIMIT, а если её мало — система выключит нейросеть, а не сайт
MemoryMax=$LIMIT
OOMScoreAdjust=800

[Install]
WantedBy=multi-user.target
EOS
systemctl daemon-reload
systemctl enable -q --now nuvora-ai
systemctl restart nuvora-ai

echo -n "    жду, пока модель загрузится"
for i in $(seq 1 90); do
  curl -sf "http://127.0.0.1:$PORT/health" >/dev/null 2>&1 && break
  echo -n "."; sleep 2
done
echo
curl -sf "http://127.0.0.1:$PORT/health" >/dev/null || { echo "Модель не запустилась. Пришлите Claude вывод: journalctl -u nuvora-ai -n 30 --no-pager"; exit 1; }

echo "==> Проверка: спрашиваю у модели"
START=$(date +%s)
ANS=$(curl -s "http://127.0.0.1:$PORT/v1/chat/completions" -H "Content-Type: application/json" \
  -d '{"model":"nuva","max_tokens":60,"messages":[{"role":"user","content":"Привет! Ответь одним предложением: как дела?"}]}' \
  | python3 -c "import json,sys;print(json.load(sys.stdin)['choices'][0]['message']['content'])" || true)
echo "    ответ за $(( $(date +%s) - START )) с: $ANS"

set_var LOCAL_AI_URL "http://127.0.0.1:$PORT/v1"
for k in GIGACHAT_AUTH_KEY GIGACHAT_SCOPE GIGACHAT_CA; do set_var $k ""; done  # GigaChat больше не используется
systemctl restart nuvora
echo
echo "Готово! Нува отвечает своей нейросетью с этого сервера. Выключить: bash $APP_DIR/deploy/set-local-ai.sh off"
