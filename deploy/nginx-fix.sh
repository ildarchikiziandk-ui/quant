#!/usr/bin/env bash
# Вместо белой «502 Bad Gateway» (сайт перезапускается или упал) — страница Нуворы, которая сама откроет сайт, когда он вернётся.
#   bash /opt/nuvora/deploy/nginx-fix.sh
set -euo pipefail
CONF=/etc/nginx/sites-available/nuvora
[ -f "$CONF" ] || { echo "Не нашёл $CONF — сначала установите сайт (install.sh)"; exit 1; }
if ! grep -q "nuvora-502" "$CONF"; then
  cp "$CONF" "$CONF.bak-$(date +%Y%m%d-%H%M)"
  # в каждый блок server, где есть proxy_pass на сайт, добавляем свою страницу ошибки
  python3 - "$CONF" <<'PY'
import re, sys
p = sys.argv[1]; s = open(p).read()
add = ("    # nuvora-502: своя страница, пока сайт перезапускается\n"
       "    error_page 502 503 504 /nuvora-502.html;\n"
       "    location = /nuvora-502.html { root /opt/nuvora/static/errors; try_files /502.html =502; internal; }\n")
out, i = [], 0
for block in re.split(r"(?=\nserver\s*\{)", s):
    if "proxy_pass http://127.0.0.1:8000" in block and "nuvora-502" not in block:
        block = block.replace("    location / {", add + "\n    location / {", 1)
    out.append(block)
open(p, "w").write("".join(out))
PY
fi
nginx -t && systemctl reload nginx
echo "Готово: вместо «502 Bad Gateway» теперь страница Нуворы «Секунду, перезагружаемся…»"
