"""Pluggable email service.

The package is split by concern — import from the concrete
submodule that owns the function:

* ``backends`` — backend Protocol, lazy backend selection,
  bounded send executor.
* ``config`` — env-driven knobs (batch size, retry sleep,
  from address).
* ``identifiers`` — Message-ID minting.
* ``observability`` — ``emit_metric`` for log-aggregation.
* ``sender`` — ``send_email`` / ``send_email_sync`` /
  ``send_with_retry``.
* ``templates`` — Jinja rendering.
* ``urls`` — absolute URL builder for in-email links.

Templates live in ``templates/{nl,en}/{name}.html`` and extend
``templates/base.html``. Each sets ``{% set subject = "..." %}``
which is extracted after rendering.
"""
