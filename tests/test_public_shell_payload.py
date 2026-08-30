"""The first-paint payload cannot break out of its ``<script>`` tag.

Every public shell is served with its data inlined, so the page is
interactive without an API round-trip. That data is organiser free text:
an event name, a location, a question label. ``json.dumps`` leaves ``<``
alone, so a name containing ``</script>`` would close the element and
have the rest of the page parsed as HTML in the body.

The nonce CSP stops any injected script from running, and on a
house-brand page the ads policy still allows an iframe and a remote
image, which is a whole page an attacker writes on our origin. So the
escaping is the fix, not the policy.
"""

import json

from backend.routers import spa

_BREAKOUT = 'Bokslessen</script><iframe src="https://evil.test"></iframe>'


def test_no_tag_can_start_inside_the_inlined_json() -> None:
    inlined = spa._inline_json({"name_nl": _BREAKOUT})
    assert "<" not in inlined
    assert ">" not in inlined
    assert "&" not in inlined


def test_the_escaped_json_still_parses_back_to_the_same_string() -> None:
    """``\\u003c`` is an ordinary JSON escape, so the page reads exactly
    what the organiser typed."""
    assert json.loads(spa._inline_json({"name_nl": _BREAKOUT}))["name_nl"] == _BREAKOUT
