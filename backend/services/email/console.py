"""Console backend — logs emails to structlog. Default for dev and CI."""

import structlog

logger = structlog.get_logger()


class ConsoleBackend:
    def send(
        self,
        to: str,
        subject: str,
        html_body: str,
        from_addr: str,
        message_id: str | None = None,
    ) -> None:
        preview = html_body[:200].replace("\n", " ")
        logger.info(
            "email_console",
            from_addr=from_addr,
            to=to,
            subject=subject,
            message_id=message_id,
            body_preview=preview,
        )
