"""DTOs for the WhatsApp blast tool's admin-only proxy routes.

Stateless: nothing here corresponds to a DB row. The shapes match
the subset of Evolution API responses the frontend actually uses,
nothing more.
"""

from typing import Literal

from pydantic import BaseModel, Field


class StatusResponse(BaseModel):
    """Connection state of the linked WhatsApp session."""

    state: Literal["open", "connecting", "close", "unknown", "not_configured"]


class QrResponse(BaseModel):
    """Pairing payload from Evolution. ``qr`` is a base64 PNG data
    URL or the raw QR string, depending on Evolution's mood; the
    frontend renders both shapes."""

    qr: str | None = None
    pairingCode: str | None = None  # noqa: N815. mirrors Evolution's field name


class HeartbeatResponse(BaseModel):
    """One round-trip for "I'm still here" + status poll."""

    state: Literal["open", "connecting", "close", "unknown", "not_configured"]


class SendRequest(BaseModel):
    """One outbound message. Phone normalisation happens client-side."""

    number: str = Field(min_length=8, max_length=20)
    text: str = Field(min_length=1, max_length=4096)


class SendResponse(BaseModel):
    """Generic ack. the frontend only cares whether it succeeded."""

    ok: bool
