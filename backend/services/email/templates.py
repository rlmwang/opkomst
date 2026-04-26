"""Jinja2 email template rendering with locale support.

Each locale lives at ``templates/{locale}/{name}.html`` and extends
``templates/base.html``. Templates set ``{% set subject = "..." %}``
which is extracted as the email subject after rendering.
"""

from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader

_env: Environment | None = None

DEFAULT_LOCALE = "nl"
SUPPORTED_LOCALES = {"nl", "en"}


def _get_env() -> Environment:
    global _env
    if _env is not None:
        return _env
    template_dir = Path(__file__).parent / "templates"
    _env = Environment(loader=FileSystemLoader(str(template_dir)), autoescape=True)
    return _env


def render(template_name: str, context: dict[str, Any], locale: str = DEFAULT_LOCALE) -> tuple[str, str]:
    """Render a localised email template. Returns ``(subject, html_body)``."""
    resolved_locale = locale if locale in SUPPORTED_LOCALES else DEFAULT_LOCALE
    context = {**context, "locale": resolved_locale}

    env = _get_env()
    template = env.get_template(f"{resolved_locale}/{template_name}")
    module = template.module  # type: ignore[reportUnknownMemberType]

    html_body: str = template.render(**context)
    subject: str = getattr(module, "subject", template_name)

    return subject, html_body
