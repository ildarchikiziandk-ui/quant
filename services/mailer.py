"""Отправка писем. Если SMTP не настроен — письма пишутся в лог, приложение продолжает работать."""
import html
import random
import smtplib
import socket
import string
import threading
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import config


def generate_code():
    return "".join(random.SystemRandom().choices(string.digits, k=6))


def _wrap(title, body_html):
    return f"""<div style="font-family:Arial,sans-serif;max-width:480px;margin:0 auto;padding:32px;">
<div style="font-size:22px;font-weight:800;color:{config.BRAND_COLOR};margin-bottom:16px;">{html.escape(config.BRAND_NAME)}</div>
<h2 style="font-size:20px;font-weight:700;margin-bottom:12px;">{title}</h2>{body_html}
<p style="color:#888;font-size:13px;margin-top:24px;">— Команда {html.escape(config.BRAND_NAME)}</p></div>"""


def _connect_ipv4(host, port, timeout):
    """Подключение только по IPv4: на многих VPS нет IPv6, и smtplib падает с «Network is unreachable»."""
    last = OSError(f"не удалось найти IPv4-адрес для {host}")
    for family, stype, proto, _, addr in socket.getaddrinfo(host, port, socket.AF_INET, socket.SOCK_STREAM):
        sock = socket.socket(family, stype, proto)
        sock.settimeout(timeout)
        try:
            sock.connect(addr)
            return sock
        except OSError as e:
            sock.close()
            last = e
    raise last


class _SMTP4(smtplib.SMTP):
    def _get_socket(self, host, port, timeout):
        return _connect_ipv4(host, port, timeout)


class _SMTPSSL4(smtplib.SMTP_SSL):
    def _get_socket(self, host, port, timeout):
        return self.context.wrap_socket(_connect_ipv4(host, port, timeout), server_hostname=self._host)


def _send_sync(to_email, subject, body):
    """Отправляет письмо. Возвращает None при успехе или текст ошибки."""
    try:
        from email.header import Header
        from email.utils import formataddr
        msg = MIMEMultipart()
        msg["From"] = formataddr((str(Header(config.BRAND_NAME, "utf-8")), config.SMTP_USER))
        msg["To"] = to_email
        if config.BRAND_EMAIL and config.BRAND_EMAIL != config.SMTP_USER:
            msg["Reply-To"] = config.BRAND_EMAIL  # ответы на письма с кодами идут в ящик для вопросов
        msg["Subject"] = Header(subject, "utf-8")
        msg.attach(MIMEText(body, "html", "utf-8"))
        if config.SMTP_PORT == 465:
            server = _SMTPSSL4(config.SMTP_HOST, config.SMTP_PORT, timeout=15)
        else:
            server = _SMTP4(config.SMTP_HOST, config.SMTP_PORT, timeout=15)
            server.starttls()
        server.login(config.SMTP_USER, config.SMTP_PASSWORD)
        server.sendmail(config.SMTP_USER, [to_email], msg.as_string())
        server.quit()
        print(f"[mail] sent to={to_email} subject={subject!r}")
        return None
    except Exception as e:
        print(f"[mail] error to={to_email}: {e}")
        return str(e)


def send(to_email, subject, body):
    if not config.EMAIL_ENABLED:
        print(f"[mail disabled] to={to_email} subject={subject}")
        return False
    threading.Thread(target=_send_sync, args=(to_email, subject, body), daemon=True).start()
    return True


def _code_block(code):
    return (f'<div style="background:#f5f3ff;border-radius:12px;padding:24px;text-align:center;margin:16px 0;">'
            f'<span style="font-size:36px;font-weight:700;letter-spacing:8px;">{code}</span></div>'
            f'<p style="color:#888;font-size:13px;">Код действителен 10 минут.</p>')


def send_verification_email(to_email, code):
    return send(to_email, f"Подтверждение email — {config.BRAND_NAME}",
                _wrap(f"Добро пожаловать в {html.escape(config.BRAND_NAME)}!", "<p>Введи этот код для подтверждения email:</p>" + _code_block(code)))


def send_reset_email(to_email, code):
    return send(to_email, f"Сброс пароля — {config.BRAND_NAME}",
                _wrap("Сброс пароля", "<p>Код для сброса пароля:</p>" + _code_block(code)
                      + "<p style='color:#888;font-size:13px;'>Если это были не вы — просто проигнорируйте письмо.</p>"))


def send_support_confirmation(to_email, subject):
    return send(to_email, f"Мы получили твоё обращение — {config.BRAND_NAME}",
                _wrap("Обращение получено", f"<p>Тема: <b>{html.escape(subject)}</b></p><p>Мы ответим в ближайшее время.</p>"))


def send_support_reply(to_email, reply_text):
    return send(to_email, f"Ответ на обращение — {config.BRAND_NAME}",
                _wrap("Ответ поддержки", f"<p>{html.escape(reply_text)}</p>"))
