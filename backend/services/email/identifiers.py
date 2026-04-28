"""RFC-5322 Message-ID minting for outbound mail."""

import secrets

from ...config import settings


def new_message_id() -> str:
    """Mint a fresh, RFC-5322-shaped Message-ID that we can quote
    on outbound mail and look up when Scaleway's bounce/complaint
    webhook fires."""
    return f"<{secrets.token_hex(16)}@{settings.message_id_domain}>"
