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
    """The tenant in scope: its id for the data, its brand for anything
    rendered. Both travel together because a write needs the first and a
    page or email needs the second, and looking one up from the other at
    every use would be a query per surface.

    ``brand`` is the folder under ``brands/``, which is an organisation's
    slug but the house brand for a personal tenant — see
    ``Tenant.brand_slug``, the one place that rule lives. Callers pass it
    rather than the slug, so nothing downstream has to know which kind
    of account it is rendering for."""

    id: str
    brand: str


_current: ContextVar[Bound | None] = ContextVar("current_tenant", default=None)


class NoTenantBound(RuntimeError):
    """Raised when something needs the tenant and nothing bound one."""


def bind(tenant_id: str, brand: str) -> None:
    """Bind the tenant for the rest of this context (request, task, CLI
    invocation). Later binds in the same context replace earlier ones.

    ``brand`` is ``Tenant.brand_slug``, never the raw slug."""
    _current.set(Bound(id=tenant_id, brand=brand))


def current() -> str:
    """The bound tenant's id. Raises ``NoTenantBound`` when there isn't
    one."""
    return _require().id


def current_brand() -> str:
    """The brand folder a page or an email in this context should wear."""
    return _require().brand


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


class CrossTenantWrite(RuntimeError):
    """Raised when a flush would write a row belonging to a different
    organisation than the one bound to this request."""


def _guard_flush(session, _flush_context, _instances) -> None:  # type: ignore[no-untyped-def]
    """The last line of defence, checked on every flush.

    Scoping lives in the routers and in ``services/access.py``, and that
    is where a request is *supposed* to be stopped. This exists for the
    case where it wasn't: a query that forgot its filter, a helper that
    fetched by id alone, a future endpoint that skips ``get_scoped``.
    Reading another organisation's row is then still a bug, but it can't
    become an edit — the write fails at the session boundary, before it
    reaches the database.

    Rows without a ``tenant_id`` (the ``tenants`` table itself) are not
    the guard's business."""
    bound = _current.get()
    for obj in (*session.new, *session.dirty):
        tenant_id = getattr(obj, "tenant_id", None)
        if tenant_id is None:
            continue
        if bound is None:
            raise NoTenantBound(f"{type(obj).__name__} written with no tenant bound")
        if tenant_id != bound.id:
            raise CrossTenantWrite(
                f"{type(obj).__name__} belongs to tenant {tenant_id}, but this request is bound to {bound.id}"
            )


def install_write_guard(session_class: type) -> None:
    """Wire ``_guard_flush`` onto every session made by this factory.
    Called once, from ``backend.database``."""
    from sqlalchemy import event

    event.listen(session_class, "before_flush", _guard_flush)


@contextmanager
def use(tenant_id: str, brand: str) -> Generator[None]:
    """Bind a tenant for the duration of a block and restore the previous
    one after: the shape the CLI, the seeds and the mail lifecycle need
    when they loop over several tenants' work in one process."""
    token = _current.set(Bound(id=tenant_id, brand=brand))
    try:
        yield
    finally:
        _current.reset(token)
