"""SMTP backend — for production (Scaleway TEM or any SMTP provider).

Reads SMTP_* config from ``settings``; the boot-time validator
guarantees ``smtp_host`` is set whenever ``email_backend == 'smtp'``.
"""

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from ...config import settings


class SmtpBackend:
    def __init__(self) -> None:
        # smtp_host / smtp_user / smtp_password are guaranteed
        # non-None when email_backend=smtp by the Settings validator.
        assert settings.smtp_host is not None
        self.host = settings.smtp_host
        self.port = settings.smtp_port
        self.user = settings.smtp_user or ""
        self.password = (
            settings.smtp_password.get_secret_value() if settings.smtp_password else ""
        )

    def send(
        self,
        to: str,
        subject: str,
        html_body: str,
        from_addr: str,
        message_id: str | None = None,
    ) -> None:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = from_addr
        msg["To"] = to
        if message_id:
            # Stable id for correlating Scaleway TEM webhook events
            # (delivery / bounce / complaint) back to a specific signup.
            msg["Message-ID"] = message_id
        msg.attach(MIMEText(html_body, "html"))

        with smtplib.SMTP(self.host, self.port, timeout=10) as server:
            server.starttls()
            if self.user:
                server.login(self.user, self.password)
            server.sendmail(from_addr, to, msg.as_string())
