/**
 * Public datepoll mini-app entry. Mounts a single component to
 * ``#app`` — no router, no Pinia, no Vue Query, no PrimeVue, no
 * vue-i18n. Mirrors ``src/public_form/main.ts`` one-to-one; same
 * wire-weight target.
 *
 * Handles exactly one URL shape (``/d/<slug>``); the slug is parsed
 * from ``window.location.pathname`` inside the component.
 */

import { createApp } from "vue";
import "@/assets/theme.css";
import PublicDatepoll from "./PublicDatepoll.vue";

createApp(PublicDatepoll).mount("#app");
