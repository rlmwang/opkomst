import os
import smtplib
import structlog
from email.message import EmailMessage

logger = structlog.get_logger()

SMTP_HOST = os.environ.get("SMTP_HOST", "")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
SMTP_FROM = os.environ.get("SMTP_FROM", "noreply@opkomst.nu")


def send_email(*, to: str, subject: str, body: str) -> None:
    """Send a plaintext email. When ``SMTP_HOST`` is unset, log to console
    so dev runs don't need an SMTP server.

    Logs only the recipient — never the body. Body content can include
    feedback-form URLs that, if logged, would correlate emails with events.
    """
    if not SMTP_HOST:
        logger.info("email_console", to=to, subject=subject)
        print(f"[EMAIL → {to}] {subject}\n{body}\n")
        return

    msg = EmailMessage()
    msg["From"] = SMTP_FROM
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as smtp:
        smtp.starttls()
        if SMTP_USER:
            smtp.login(SMTP_USER, SMTP_PASSWORD)
        smtp.send_message(msg)
    logger.info("email_sent", to=to, subject=subject)
