"""SMTP 发信。连接方式由配置决定：none（开发/测试的 Mailpit）、starttls（587）、ssl（465）。"""

import smtplib
from email.message import EmailMessage

from app.config import Settings


class EmailDisabledError(RuntimeError):
    """未配置 SMTP（smtp_host 为空）时调用发信。"""


def build_message(settings: Settings, to: str, subject: str, body: str) -> EmailMessage:
    message = EmailMessage()
    message["From"] = settings.mail_from
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)
    return message


def send_mail(settings: Settings, to: str, subject: str, body: str, timeout: float = 10) -> None:
    if not settings.email_enabled:
        raise EmailDisabledError("未配置 SMTP_HOST，邮件发送已关闭")
    message = build_message(settings, to, subject, body)
    if settings.smtp_security == "ssl":
        client = smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=timeout)
    else:
        client = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=timeout)
    with client:
        if settings.smtp_security == "starttls":
            client.starttls()
        if settings.smtp_username:
            client.login(settings.smtp_username, settings.smtp_password)
        client.send_message(message)
