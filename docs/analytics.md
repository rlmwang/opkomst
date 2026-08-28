# Knowing what the traffic is

Status: partly built. Counting happens; there is no dashboard.

The constraint comes first: no third-party analytics, no tracking
pixels, no cookies for measurement. That rules out the usual tools, and
it rules them out on the organiser side too, not only on the public
pages.

What exists instead is a counter per surface and per day, incremented
server-side when a public page is viewed or submitted. It records what
kind of page it was and nothing about who opened it: no address, no
identifier, no path that could name an entity.

`python -m backend.cli traffic-report` prints it. There is no page for
it on purpose. Traffic is platform-level, like the tenant list and the
brand folders, and neither of those has a UI either.
