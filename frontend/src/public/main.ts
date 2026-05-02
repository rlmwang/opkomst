/**
 * Public sign-up mini-app entry. Mounts a single component to
 * ``#app`` — no router, no Pinia, no Vue Query, no PrimeVue, no
 * vue-i18n.
 *
 * The page handles exactly one URL shape (``/e/<slug>``); the slug
 * is parsed from ``window.location.pathname`` directly.
 *
 * Imports the shared ``theme.css`` so brand classes (``.container``,
 * ``.card``, ``.stack``, ``.muted``, etc.) and CSS custom
 * properties (--brand-red, --brand-bg, ...) are available — same
 * visual language as the admin SPA. The PrimeVue-specific overrides
 * inside theme.css are inert here because PrimeVue isn't loaded.
 */

import { createApp } from "vue";
import "@/assets/theme.css";
import PublicEvent from "./PublicEvent.vue";

createApp(PublicEvent).mount("#app");
