"""RFC-5322 Message-ID minting for outbound mail."""

import os
import secrets


def new_message_id() -> str:
    """Mint a fresh, RFC-5322-shaped Message-ID that we can quote
    on outbound mail and look up when Scaleway's bounce/complaint
    webhook fires. The domain is required: a missing
    ``MESSAGE_ID_DOMAIN`` is a deploy bug, not something to paper
    over with a localhost fallback."""
    domain = os.environ["MESSAGE_ID_DOMAIN"]
    return f"<{secrets.token_hex(16)}@{domain}>"
