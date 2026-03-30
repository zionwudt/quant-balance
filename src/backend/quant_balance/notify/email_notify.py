"""SMTP 邮件通知。"""

from __future__ import annotations

from email.message import EmailMessage
import smtplib

from quant_balance.notify.base import Notifier


class EmailNotifier(Notifier):
    """SMTP 邮件通知。"""

    channel = "email"

    def __init__(
        self,
        *,
        smtp_host: str,
        smtp_port: int = 465,
        sender: str,
        receiver: str,
        password: str,
        username: str | None = None,
        use_ssl: bool = True,
        starttls: bool = True,
    ) -> None:
        self.smtp_host = str(smtp_host or "").strip()
        self.smtp_port = int(smtp_port)
        self.sender = str(sender or "").strip()
        self.receiver = str(receiver or "").strip()
        self.password = str(password or "").strip()
        self.username = str(username or "").strip()
        self.use_ssl = bool(use_ssl)
        self.starttls = bool(starttls)

        if not self.smtp_host:
            raise ValueError("notify.email.smtp_host 未配置。")
        if not self.sender:
            raise ValueError("notify.email.sender 未配置。")
        if not self.receiver:
            raise ValueError("notify.email.receiver 未配置。")
        if not self.password:
            raise ValueError("notify.email.password 未配置。")

    def send(self, title: str, content: str) -> bool:
        message = EmailMessage()
        message["Subject"] = title
        message["From"] = self.sender
        message["To"] = self.receiver
        message.set_content(content)

        smtp_cls = smtplib.SMTP_SSL if self.use_ssl else smtplib.SMTP
        with smtp_cls(self.smtp_host, self.smtp_port, timeout=10) as client:
            if not self.use_ssl and self.starttls:
                client.starttls()
            client.login(self.username or self.sender, self.password)
            client.send_message(message)
        return True
