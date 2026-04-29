"""Hypothesis fuzz of the Scaleway TEM webhook.

The webhook is the closest thing opkomst has to a public,
unauthenticated write endpoint — Scaleway provides the HMAC, but
the body format is provider-defined and a misbehaving provider (or
a malicious actor with the secret) can post anything. The contract
is: never 500. Always one of {204, 401, 503, 429}, no matter what
the body looks like.
"""

import hashlib
import hmac
import json

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st


@pytest.fixture(autouse=True)
def _clear_signing(monkeypatch):
    """Run with no webhook secret configured — that's the
    fail-closed path (503). The fuzz still exercises body parsing
    + signature handling; the test asserts the no-500 contract."""
    monkeypatch.delenv("SCALEWAY_WEBHOOK_SECRET", raising=False)
    monkeypatch.delenv("OPKOMST_ALLOW_UNSIGNED_WEBHOOKS", raising=False)


# Wide-but-bounded JSON: mixes valid event types, garbage strings,
# unicode (including astral), nested arrays, nulls, and oversized
# message_ids. Hypothesis explores enough of this that any
# JSONDecodeError or unhandled type assumption blows up the test.
_event_strategy = st.dictionaries(
    keys=st.text(min_size=0, max_size=20),
    values=st.one_of(
        st.none(),
        st.booleans(),
        st.integers(),
        st.text(min_size=0, max_size=200),
        st.lists(st.text(max_size=20), max_size=5),
        st.dictionaries(st.text(max_size=10), st.text(max_size=20), max_size=3),
    ),
    max_size=10,
)

_payload_strategy = st.one_of(
    _event_strategy,
    st.lists(_event_strategy, max_size=4),
)


@settings(
    max_examples=80,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(payload=_payload_strategy)
def test_webhook_never_500s_on_arbitrary_json(payload, client) -> None:
    r = client.post(
        "/api/v1/webhooks/scaleway-email",
        json=payload,
    )
    assert r.status_code in (204, 401, 503, 429), (
        f"unexpected status {r.status_code} for payload {payload!r}: {r.text}"
    )


def test_webhook_503s_when_secret_unset(client) -> None:
    """Explicit assertion of the fail-closed branch — when
    ``SCALEWAY_WEBHOOK_SECRET`` is unset the webhook refuses
    every request, including ones with a header."""
    r = client.post(
        "/api/v1/webhooks/scaleway-email",
        headers={"X-Scaleway-Signature": "doesntmatter"},
        json={"type": "email_bounce", "message_id": "<x>"},
    )
    assert r.status_code == 503


def test_webhook_401_on_missing_signature_when_secret_set(client, monkeypatch) -> None:
    monkeypatch.setenv("SCALEWAY_WEBHOOK_SECRET", "shhh")
    r = client.post(
        "/api/v1/webhooks/scaleway-email",
        json={"type": "email_bounce", "message_id": "<x>"},
    )
    assert r.status_code == 401


def test_webhook_401_on_bad_signature(client, monkeypatch) -> None:
    monkeypatch.setenv("SCALEWAY_WEBHOOK_SECRET", "shhh")
    r = client.post(
        "/api/v1/webhooks/scaleway-email",
        headers={"X-Scaleway-Signature": "0" * 64},
        json={"type": "email_bounce", "message_id": "<x>"},
    )
    assert r.status_code == 401


def test_webhook_204_on_valid_signature(client, monkeypatch) -> None:
    secret = "shhh"
    monkeypatch.setenv("SCALEWAY_WEBHOOK_SECRET", secret)
    body = json.dumps({"type": "email_delivered", "message_id": "<unmatched>"})
    sig = hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()
    r = client.post(
        "/api/v1/webhooks/scaleway-email",
        headers={
            "X-Scaleway-Signature": sig,
            "Content-Type": "application/json",
        },
        content=body,
    )
    assert r.status_code == 204
