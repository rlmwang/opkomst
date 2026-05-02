"""App-wide brand constants.

One source of truth so a rename (or a multi-tenant fork) doesn't
require sweeping every template + locale string by hand. The
``render`` step in ``services.mail`` injects
``app_name`` into every email context automatically; routers
that need the name in non-email contexts import ``APP_NAME``
directly."""

APP_NAME = "opkomst.nu"
