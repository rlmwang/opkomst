"""Which tenant the current unit of work belongs to.

Every table carries ``tenant_id`` NOT NULL, so every insert needs one.
Rather than repeat it at each of the ~60 creation sites — where it would
eventually be forgotten — the column's default reads the tenant bound to
this context, and the callers that *know* the tenant bind it once:

* organiser requests — ``auth.get_current_user`` binds the signed-in
  user's tenant, so nothing an organiser creates can land anywhere else;
* public requests — the router binds the tenant of the entity the URL
  resolved to (the event behind ``/e/{slug}``, the roster behind
  ``/c/{slug}``), which is how a page with no tenant in its URL still
  writes into the right one;
* the CLI, the seeds and the lifecycle worker — bind explicitly around
  the work they do.

Reading an unbound tenant raises. A write with no tenant in scope is a
bug, and it should surface at the point it happens rather than as a
constraint violation three frames later.
"""

from collections.abc import Generator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass


@dataclass(frozen=True)
class Bound:
    """The tenant in scope: its id for the data, its slug for the brand.
    Both travel together because a write needs the first and a rendered
    page or email needs the second, and looking one up from the other at
    every use would be a query per surface."""

    id: str
    slug: str


_current: ContextVar[Bound | None] = ContextVar("current_tenant", default=None)


class NoTenantBound(RuntimeError):
    """Raised when something needs the tenant and nothing bound one."""


def bind(tenant_id: str, slug: str) -> None:
    """Bind the tenant for the rest of this context (request, task, CLI
    invocation). Later binds in the same context replace earlier ones."""
    _current.set(Bound(id=tenant_id, slug=slug))


def current() -> str:
    """The bound tenant's id. Raises ``NoTenantBound`` when there isn't
    one."""
    return _require().id


def current_slug() -> str:
    """The bound tenant's slug — the brand folder a page or an email
    should wear."""
    return _require().slug


def current_or_none() -> Bound | None:
    """The bound tenant, or ``None``. For read paths that want to know
    whether they are inside a tenant without insisting on it."""
    return _current.get()


def _require() -> Bound:
    bound = _current.get()
    if bound is None:
        raise NoTenantBound(
            "No tenant is bound for this request. Organiser routes bind it from the "
            "signed-in user; public routes bind it from the entity the slug resolved to."
        )
    return bound


@contextmanager
def use(tenant_id: str, slug: str) -> Generator[None]:
    """Bind a tenant for the duration of a block and restore the previous
    one after — the shape the CLI, the seeds and the mail lifecycle need
    when they loop over several tenants' work in one process."""
    token = _current.set(Bound(id=tenant_id, slug=slug))
    try:
        yield
    finally:
        _current.reset(token)
