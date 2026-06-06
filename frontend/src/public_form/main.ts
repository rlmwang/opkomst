/**
 * Public form mini-app entry. Mounts a single component to
 * ``#app`` — no router, no Pinia, no Vue Query, no PrimeVue, no
 * vue-i18n. Mirrors ``src/public/main.ts`` (the event sign-up
 * mini-app) one-to-one; same wire-weight target.
 *
 * Handles exactly one URL shape (``/f/<slug>``); the slug is
 * parsed from ``window.location.pathname`` directly.
 */

import { createApp } from "vue";
import "@/assets/theme.css";
import PublicForm from "./PublicForm.vue";

createApp(PublicForm).mount("#app");
