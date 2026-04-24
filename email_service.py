import smtplib
import random
import string
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

SMTP_HOST = "smtp.mail.ru"
SMTP_PORT = 587
SMTP_USER = "quantru@internet.ru"
SMTP_PASSWORD = "XBpaf5FNr3C5dIuOwdRb"

def generate_code():
    return ''.join(random.choices(string.digits, k=6))

def _send(to_email, subject, body):
    try:
        msg = MIMEMultipart()
        msg['From'] = SMTP_USER
        msg['To'] = to_email
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'html'))
        server = smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=5)
        server.starttls()
        server.login(SMTP_USER, SMTP_PASSWORD)
        server.sendmail(SMTP_USER, to_email, msg.as_string())
        server.quit()
        return True
    except Exception as e:
        print(f"Email error: {e}")
        return False

def send_verification_email(to_email: str, code: str):
    body = f"""<div style="font-family:Arial,sans-serif;max-width:480px;margin:0 auto;padding:32px;">
        <h2 style="font-size:24px;font-weight:700;margin-bottom:8px;">Добро пожаловать в Quant ⚡</h2>
        <p style="color:#555;margin-bottom:24px;">Введи этот код для подтверждения email:</p>
        <div style="background:#f5f5f5;border-radius:12px;padding:24px;text-align:center;margin-bottom:24px;">
            <span style="font-size:36px;font-weight:700;letter-spacing:8px;">{code}</span>
        </div>
        <p style="color:#888;font-size:13px;">Код действителен 10 минут.</p>
    </div>"""
    return _send(to_email, "Подтверждение email — Quant", body)

def send_support_confirmation(to_email: str, subject: str):
    body = f"""<div style="font-family:Arial,sans-serif;max-width:480px;margin:0 auto;padding:32px;">
        <h2 style="font-size:22px;font-weight:700;margin-bottom:8px;">Обращение получено ⚡</h2>
        <p style="color:#555;margin-bottom:16px;">Тема: <b>{subject}</b></p>
        <p style="color:#555;">Мы рассмотрим твоё обращение и ответим в ближайшее время.</p>
        <p style="color:#888;font-size:13px;margin-top:24px;">— Команда Quant</p>
    </div>"""
    return _send(to_email, "Мы получили твоё обращение — Quant", body)

def send_support_reply(to_email: str, reply_text: str):
    body = f"""<div style="font-family:Arial,sans-serif;max-width:480px;margin:0 auto;padding:32px;">
        <h2 style="font-size:22px;font-weight:700;margin-bottom:8px;">Ответ от команды Quant ⚡</h2>
        <p style="color:#555;margin-bottom:16px;">{reply_text}</p>
        <p style="color:#888;font-size:13px;margin-top:24px;">— Команда Quant</p>
    </div>"""
    return _send(to_email, "Ответ на ваше обращение — Quant", body)