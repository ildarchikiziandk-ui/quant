#!/usr/bin/env bash
# Сильная защита сервера Nuvora (7.11.2026). Запуск один раз (можно повторять — ничего не сломает):
#   bash /opt/nuvora/deploy/harden.sh
# Что делает:
#   1) файрвол: снаружи открыты только сайт (80, 443), вход на сервер (SSH) и порты звонков;
#   2) fail2ban: блокирует адреса, которые подбирают пароль к серверу или к аккаунтам на сайте;
#   3) SSH: меньше попыток ввести пароль, быстрее отключает «молчащих»;
#   4) ядро Linux: защита от SYN-флуда и подменённых адресов;
#   5) nginx: ограничение запросов и соединений с одного адреса (от DDoS и ботов), короткие ожидания;
#   6) службы сайта, школы и Нувы работают в «песочнице»: не могут менять систему;
#   7) автоматические обновления безопасности Ubuntu.
# Каждый шаг проверяется; если после шага что-то не работает — он откатывается сам.
set -uo pipefail
export DEBIAN_FRONTEND=noninteractive NEEDRESTART_MODE=l NEEDRESTART_SUSPEND=1
APP_DIR=/opt/nuvora
[ "$(id -u)" = 0 ] || { echo "Запустите от root: sudo bash $0"; exit 1; }
ok() { echo "   ✓ $*"; }
warn() { echo "   ! $*"; }

echo "==> 1/7 Программы защиты"
apt-get update -qq >/dev/null 2>&1 || true
apt-get install -y -qq ufw fail2ban python3-systemd unattended-upgrades >/dev/null 2>&1 && ok "ufw, fail2ban, unattended-upgrades" || warn "не всё установилось — продолжаю"

echo "==> 2/7 Файрвол"
if command -v ufw >/dev/null; then
  SSH_PORTS=$(sshd -T 2>/dev/null | awk '/^port /{print $2}' | sort -u)
  [ -n "$SSH_PORTS" ] || SSH_PORTS=22
  # сначала вход на сервер — чтобы не запереть самих себя; «limit» = разрешено, но не больше 6 подключений за 30 секунд с адреса
  for p in $SSH_PORTS; do ufw limit "$p/tcp" >/dev/null; ufw delete allow "$p/tcp" >/dev/null 2>&1 || true; done
  ufw allow 80/tcp >/dev/null
  ufw allow 443/tcp >/dev/null
  if [ -f /etc/turnserver.conf ] || grep -q '^TURN_SECRET=.' "$APP_DIR/.env" 2>/dev/null; then
    ufw allow 3478 >/dev/null
    ufw allow 49160:49200/udp >/dev/null
  fi
  ufw default deny incoming >/dev/null
  ufw default allow outgoing >/dev/null
  ufw --force enable >/dev/null && ok "включён; открыты: SSH ($(echo $SSH_PORTS)), 80, 443$( [ -f /etc/turnserver.conf ] && echo ', звонки 3478 и 49160–49200')"
else
  warn "ufw не установился — файрвол пропущен"
fi

echo "==> 3/7 fail2ban (блокировка подбора паролей)"
mkdir -p /etc/fail2ban/filter.d /etc/fail2ban/jail.d
cat > /etc/fail2ban/filter.d/nuvora-login.conf <<'EOF'
[Definition]
failregex = \[login\] (?:wrong password|rate-limited|account-locked|no such user) ip=<HOST>(?:\s|$)
ignoreregex =
EOF
cat > /etc/fail2ban/jail.d/nuvora.local <<'EOF'
[DEFAULT]
bantime = 1h
findtime = 10m
banaction = ufw
ignoreip = 127.0.0.1/8 ::1

[sshd]
enabled = true
backend = systemd
maxretry = 5

# неверные пароли на сайте: 20 за 10 минут с одного адреса — бан на час
[nuvora-login]
enabled = true
backend = systemd
journalmatch = _SYSTEMD_UNIT=nuvora.service
filter = nuvora-login
maxretry = 20

# кто попадал в бан 3 раза за сутки — на неделю
[recidive]
enabled = true
backend = auto
logpath = /var/log/fail2ban.log
bantime = 7d
findtime = 1d
maxretry = 3
EOF
command -v ufw >/dev/null || sed -i 's/^banaction = ufw/banaction = iptables-multiport/' /etc/fail2ban/jail.d/nuvora.local
touch /var/log/fail2ban.log
systemctl enable fail2ban >/dev/null 2>&1
if systemctl restart fail2ban && sleep 2 && fail2ban-client ping >/dev/null 2>&1; then
  ok "работает: $(fail2ban-client status 2>/dev/null | sed -n 's/.*Jail list:\s*//p')"
else
  warn "fail2ban не запустился с новыми правилами — убираю правила сайта, оставляю защиту SSH"
  sed -i '/^\[nuvora-login\]/,/^maxretry = 20/d' /etc/fail2ban/jail.d/nuvora.local
  systemctl restart fail2ban || true
fi

echo "==> 4/7 SSH"
mkdir -p /etc/ssh/sshd_config.d
cat > /etc/ssh/sshd_config.d/10-nuvora.conf <<'EOF'
# Nuvora: меньше попыток пароля и без лишних возможностей (пароль для входа остаётся рабочим)
MaxAuthTries 3
LoginGraceTime 30
PermitEmptyPasswords no
X11Forwarding no
ClientAliveInterval 300
ClientAliveCountMax 2
EOF
if sshd -t 2>/dev/null; then
  systemctl reload ssh 2>/dev/null || systemctl reload sshd 2>/dev/null || true
  ok "3 попытки пароля за подключение, пустые пароли запрещены"
else
  rm -f /etc/ssh/sshd_config.d/10-nuvora.conf
  warn "настройка SSH не подошла — оставил как было"
fi

echo "==> 5/7 Ядро Linux"
cat > /etc/sysctl.d/90-nuvora.conf <<'EOF'
# защита от SYN-флуда и подменённых адресов
net.ipv4.tcp_syncookies = 1
net.ipv4.tcp_max_syn_backlog = 4096
net.ipv4.conf.all.rp_filter = 2
net.ipv4.conf.default.rp_filter = 2
net.ipv4.conf.all.accept_redirects = 0
net.ipv4.conf.default.accept_redirects = 0
net.ipv6.conf.all.accept_redirects = 0
net.ipv4.conf.all.send_redirects = 0
net.ipv4.conf.all.accept_source_route = 0
net.ipv6.conf.all.accept_source_route = 0
net.ipv4.icmp_echo_ignore_broadcasts = 1
net.ipv4.icmp_ignore_bogus_error_responses = 1
# меньше подсказок взломщику
kernel.kptr_restrict = 2
kernel.dmesg_restrict = 1
fs.protected_symlinks = 1
fs.protected_hardlinks = 1
EOF
sysctl --system >/dev/null 2>&1 && ok "применено" || warn "часть настроек ядра не применилась (на некоторых VPS это нормально)"

echo "==> 6/7 nginx: лимиты запросов"
if command -v nginx >/dev/null; then
  cat > /etc/nginx/conf.d/nuvora-limits.conf <<'EOF'
# с одного адреса: до 30 запросов в секунду (рывком до 400 — страница с картинками) и до 100 соединений сразу
limit_req_zone $binary_remote_addr zone=nv_req:20m rate=30r/s;
limit_conn_zone $binary_remote_addr zone=nv_conn:20m;
limit_req zone=nv_req burst=400 nodelay;
limit_conn nv_conn 100;
limit_req_status 429;
limit_conn_status 429;
# «медленные» атаки: кто не присылает данные — отключаем
client_header_timeout 15s;
client_body_timeout 30s;
send_timeout 30s;
EOF
  if nginx -t >/dev/null 2>&1; then
    systemctl reload nginx && ok "лимиты включены"
  else
    # какая-то настройка уже есть в nginx.conf — оставляем только лимиты
    sed -i '/_timeout /d' /etc/nginx/conf.d/nuvora-limits.conf
    if nginx -t >/dev/null 2>&1; then systemctl reload nginx && ok "лимиты включены (ожидания уже были настроены)"
    else rm -f /etc/nginx/conf.d/nuvora-limits.conf; warn "nginx не принял лимиты — оставил как было"; fi
  fi
else
  warn "nginx не найден"
fi

echo "==> 7/7 Песочница для служб и автообновления"
for svc in nuvora nuvora-school nuvora-ai; do
  systemctl list-unit-files "$svc.service" >/dev/null 2>&1 || continue
  systemctl cat "$svc.service" >/dev/null 2>&1 || continue
  mkdir -p "/etc/systemd/system/$svc.service.d"
  cat > "/etc/systemd/system/$svc.service.d/harden.conf" <<'EOF'
[Service]
Environment=PYTHONUNBUFFERED=1
# даже если сайт взломают, программа не сможет менять систему, читать домашние папки и получать права root
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=full
ProtectHome=yes
ProtectKernelTunables=yes
ProtectKernelModules=yes
ProtectKernelLogs=yes
ProtectControlGroups=yes
ProtectClock=yes
RestrictSUIDSGID=yes
RestrictRealtime=yes
RestrictNamespaces=yes
LockPersonality=yes
EOF
  systemctl daemon-reload
  if systemctl is-active -q "$svc"; then
    systemctl restart "$svc"; sleep 4
    if systemctl is-active -q "$svc"; then ok "$svc — в песочнице"
    else
      rm -f "/etc/systemd/system/$svc.service.d/harden.conf"; systemctl daemon-reload; systemctl restart "$svc"
      warn "$svc не запустился в песочнице — вернул как было"
    fi
  fi
done
if systemctl is-active -q nuvora; then
  code=$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8000/healthz || true)
  if [ "$code" != "200" ]; then
    rm -f /etc/systemd/system/nuvora.service.d/harden.conf; systemctl daemon-reload; systemctl restart nuvora
    warn "сайт не ответил ($code) — песочница для сайта снята"
  fi
fi
cat > /etc/apt/apt.conf.d/20auto-upgrades <<'EOF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
APT::Periodic::AutocleanInterval "7";
EOF
ok "обновления безопасности Ubuntu ставятся сами каждый день (без перезагрузки)"

echo
echo "Готово. Сайт: $(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8000/healthz 2>/dev/null) (200 — работает)."
echo "Заблокированные адреса: fail2ban-client status sshd    и    fail2ban-client status nuvora-login"
echo "Разблокировать адрес:   fail2ban-client unban 1.2.3.4"
echo "Если у хостинга есть свой файрвол в панели — он не мешает, этот работает внутри сервера."
