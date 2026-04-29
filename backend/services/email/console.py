"""Console backend — logs emails to structlog. Default for dev and CI."""

import re

import structlog

logger = structlog.get_logger()

# Extract every absolute http(s) link from the rendered body so a
# dev can copy-paste the magic link straight from the log line.
# HTML escapes ``&`` as ``&amp;`` in token query strings; un-escape
# so the URL is paste-ready.
_URL_RE = re.compile(r'href=["\'](https?://[^"\']+)["\']')


class ConsoleBackend:
    def send(
        self,
        to: str,
        subject: str,
        html_body: str,
        from_addr: str,
        message_id: str | None = None,
    ) -> None:
        urls = [m.replace("&amp;", "&") for m in _URL_RE.findall(html_body)]
        logger.info(
            "email_console",
            from_addr=from_addr,
            to=to,
            subject=subject,
            message_id=message_id,
            urls=urls,
        )
