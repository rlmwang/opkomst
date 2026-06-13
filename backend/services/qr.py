"""Shared QR-code rendering.

Both the public event sign-up page and the public form page hand
out a QR that resolves to their respective ``/e/{slug}`` /
``/f/{slug}`` URL. The rendering is identical: pure-Python SVG-path
output (no PIL), transparent background, ~1–2 KB of losslessly
scalable markup. A per-process LRU keeps repeat fetches at memory
speed; the cache key is the full target URL so the two surfaces
never collide.
"""

import io
from functools import lru_cache

import qrcode
import qrcode.image.svg


@lru_cache(maxsize=256)
def render_qr(target_url: str) -> bytes:
    """SVG bytes for a QR encoding ``target_url``. SVG-path rendering
    is pure-Python and transparent by default — dark modules are
    ``<path>`` elements, the background is empty, so the QR sits on
    whatever surface composites it."""
    qr = qrcode.QRCode(box_size=10, border=2, image_factory=qrcode.image.svg.SvgPathImage)
    qr.add_data(target_url)
    qr.make(fit=True)
    buf = io.BytesIO()
    qr.make_image().save(buf)
    return buf.getvalue()
