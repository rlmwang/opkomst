"""AES-GCM encryption for one-time email storage.

Used exclusively to encrypt attendee emails before they hit the
database, and to decrypt them inside the feedback worker. No other
code path is allowed to call ``decrypt`` — see CLAUDE.md "Privacy
invariants".
"""

import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_KEY_B64 = os.environ["EMAIL_ENCRYPTION_KEY"]
_KEY = base64.b64decode(_KEY_B64)
if len(_KEY) != 32:
    raise RuntimeError("EMAIL_ENCRYPTION_KEY must decode to exactly 32 bytes (AES-256)")

_aesgcm = AESGCM(_KEY)


def encrypt(plaintext: str) -> bytes:
    """Encrypt a plaintext email. Output is 12-byte nonce || ciphertext+tag."""
    nonce = os.urandom(12)
    ct = _aesgcm.encrypt(nonce, plaintext.encode("utf-8"), associated_data=None)
    return nonce + ct


def decrypt(blob: bytes) -> str:
    """Decrypt a blob produced by ``encrypt``. Raises ``InvalidTag`` if the
    blob has been tampered with."""
    nonce, ct = blob[:12], blob[12:]
    return _aesgcm.decrypt(nonce, ct, associated_data=None).decode("utf-8")
