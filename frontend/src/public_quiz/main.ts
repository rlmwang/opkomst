/**
 * Public quiz mini-app entry. Mounts one component to ``#app`` — no
 * router, no Pinia, no Vue Query, no PrimeVue, no vue-i18n, the same
 * wire-weight target as the other four.
 *
 * Handles one URL shape (``/q/<slug>``); the slug is parsed from
 * ``window.location.pathname`` directly.
 */

import { createApp } from "vue";
import "@/assets/theme.css";
import "@/public_shared/forms.css";
import PublicQuiz from "./PublicQuiz.vue";

createApp(PublicQuiz).mount("#app");
