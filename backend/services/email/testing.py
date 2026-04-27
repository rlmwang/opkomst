"""Test-only email backend.

Records every ``send`` call into a list so tests can assert what
was sent without spinning up SMTP. Plug it in by calling
``install_fake_backend()`` (or the pytest fixture in
``tests/conftest.py``); call ``uninstall()`` in teardown.

Each captured email is exposed as a ``CapturedEmail`` dataclass —
fields match the ``EmailBackend`` protocol's ``send`` signature.
"""

from dataclasses import dataclass, field


@dataclass
class CapturedEmail:
    to: str
    subject: str
    html_body: str
    from_addr: str
    message_id: str | None = None


@dataclass
class FakeBackend:
    """Records ``send`` calls instead of dispatching them.

    Tests can either inspect ``sent`` directly or register
    behaviour overrides via ``raise_on`` to simulate SMTP failure
    for specific recipients (or all of them).
    """

    sent: list[CapturedEmail] = field(default_factory=list)
    raise_on: set[str] | None = None  # ``None`` = never raise; ``set()`` = raise for every recipient
    _raises_remaining: dict[str, int] = field(default_factory=dict)

    def send(
        self,
        to: str,
        subject: str,
        html_body: str,
        from_addr: str,
        message_id: str | None = None,
    ) -> None:
        # Simulate SMTP failure when configured. ``raise_on`` is a
        # set of recipient addresses (or empty set = match all).
        if self.raise_on is not None and (not self.raise_on or to in self.raise_on):
            remaining = self._raises_remaining.get(to)
            if remaining is None or remaining > 0:
                if remaining is not None:
                    self._raises_remaining[to] = remaining - 1
                raise RuntimeError(f"FakeBackend forced failure for {to}")
        self.sent.append(
            CapturedEmail(
                to=to,
                subject=subject,
                html_body=html_body,
                from_addr=from_addr,
                message_id=message_id,
            )
        )

    # ---- helpers used in test assertions ----

    def to(self, recipient: str) -> list[CapturedEmail]:
        """Every captured mail addressed to ``recipient``."""
        return [m for m in self.sent if m.to == recipient]

    def of_template(self, marker: str) -> list[CapturedEmail]:
        """Every captured mail whose subject *or* body contains
        ``marker`` — handy for asserting that a specific template
        rendered without depending on the exact subject string."""
        return [m for m in self.sent if marker in m.subject or marker in m.html_body]

    def reset(self) -> None:
        self.sent.clear()
        self._raises_remaining.clear()

    def fail_n_times(self, recipient: str, n: int) -> None:
        """Raise on the first ``n`` calls to ``recipient``, then
        succeed. Useful for testing the worker's two-attempt
        retry loop."""
        if self.raise_on is None:
            self.raise_on = set()
        self.raise_on.add(recipient)
        self._raises_remaining[recipient] = n


# --- install / uninstall hooks --------------------------------------

def install_fake_backend() -> FakeBackend:
    """Replace the singleton backend with a fresh ``FakeBackend``
    and return it. Idempotent: re-installs cleanly even if the
    previous install wasn't torn down."""
    from backend.services import email as email_module

    fake = FakeBackend()
    email_module._backend = fake
    return fake


def uninstall() -> None:
    """Reset the email module's singleton so the next ``get_backend``
    rebuilds from environment (typical: console backend in tests)."""
    from backend.services import email as email_module

    email_module._backend = None
