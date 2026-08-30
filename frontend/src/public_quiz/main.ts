/**
 * Public quiz mini-app entry. Mounts one component to ``#app`` — no
 * router, no Pinia, no Vue Query, no vue-i18n, the same
 * wire-weight target as the other four.
 *
 * Handles one URL shape (``/q/<slug>``); the slug is parsed from
 * ``window.location.pathname`` directly.
 */

import "@/assets/theme.css";
import "@/public_shared/forms.css";
import { mountApp } from "@/lib/mount";
import PublicQuiz from "./PublicQuiz.svelte";

mountApp(PublicQuiz);
