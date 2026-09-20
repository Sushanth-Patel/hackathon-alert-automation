"""Email notifier using SMTP (disabled by default, requires zero secrets when disabled)."""

from __future__ import annotations
import os
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Union, List
from notifiers.base import BaseNotifier

logger = logging.getLogger(__name__)


class EmailNotifier(BaseNotifier):
    """SMTP Email Notifier (optional add-on, disabled by default in config.yaml)."""

    def __init__(
        self,
        enabled: bool = False,
        host: str | None = None,
        port: int | None = None,
        user: str | None = None,
        password: str | None = None,
        recipient: str | None = None,
    ):
        super().__init__(name="email", enabled=enabled)
        # Only read environment variables if explicitly enabled
        if self.enabled:
            self.host = host or os.getenv("SMTP_HOST", "smtp.gmail.com")
            self.port = int(port or os.getenv("SMTP_PORT", "587"))
            self.user = user or os.getenv("SMTP_USER", "")
            self.password = password or os.getenv("SMTP_PASSWORD", "")
            self.recipient = recipient or os.getenv("EMAIL_TO", "")
        else:
            self.host = ""
            self.port = 587
            self.user = ""
            self.password = ""
            self.recipient = ""

    def send(self, content: Union[str, List[str]]) -> bool:
        if not self.enabled:
            logger.debug("Email notifier is disabled in config. Skipping.")
            return True

        if not self.user or not self.password or not self.recipient:
            logger.error("Email notifier is enabled but SMTP credentials or recipient are missing!")
            return False

        html_body = content if isinstance(content, str) else "\n<hr/>\n".join(content)

        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = "🗓 Hackathon Alert Digest"
            msg["From"] = self.user
            msg["To"] = self.recipient
            msg.attach(MIMEText(html_body, "html"))

            with smtplib.SMTP(self.host, self.port, timeout=20) as server:
                server.starttls()
                server.login(self.user, self.password)
                server.send_message(msg)

            logger.info("Successfully sent digest email to %s", self.recipient)
            return True
        except Exception as e:
            logger.error("Failed to send email notification: %s", e, exc_info=True)
            return False
