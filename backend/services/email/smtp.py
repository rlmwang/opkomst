"""SMTP backend — for production. Reads SMTP_HOST/SMTP_PORT/SMTP_USER/SMTP_PASSWORD from env."""

import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


class SmtpBackend:
    def __init__(self) -> None:
        self.host = os.environ["SMTP_HOST"]
        self.port = int(os.environ.get("SMTP_PORT", "587"))
        self.user = os.environ.get("SMTP_USER", "")
        self.password = os.environ.get("SMTP_PASSWORD", "")

    def send(self, to: str, subject: str, html_body: str, from_addr: str) -> None:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = from_addr
        msg["To"] = to
        msg.attach(MIMEText(html_body, "html"))

        with smtplib.SMTP(self.host, self.port, timeout=10) as server:
            server.starttls()
            if self.user:
                server.login(self.user, self.password)
            server.sendmail(from_addr, to, msg.as_string())
