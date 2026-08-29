/**
 * Public sign-up mini-app entry. Mounts a single component to
 * ``#app``: no router, no Pinia, no Vue Query, no vue-i18n.
 *
 * The page handles exactly one URL shape (``/e/<slug>``); the slug
 * is parsed from ``window.location.pathname`` directly.
 *
 * Imports the shared ``theme.css`` so brand classes (``.container``,
 * ``.card``, ``.stack``, ``.muted``, etc.) and CSS custom
 * properties (--brand-red, --brand-bg, ...) are available: the same
 * visual language as the admin SPA.
 */

import { mount } from "svelte";
import "@/assets/theme.css";
import "@/public_shared/forms.css";
import PublicEvent from "./PublicEvent.svelte";

mount(PublicEvent, { target: document.getElementById("app")! });
