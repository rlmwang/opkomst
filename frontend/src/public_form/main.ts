/**
 * Public form mini-app entry. Mounts a single component to
 * ``#app``: no router, no Pinia, no Vue Query, no
 * vue-i18n. Mirrors ``src/public/main.ts`` (the event sign-up
 * mini-app) one-to-one; same wire-weight target.
 *
 * Handles exactly one URL shape (``/f/<slug>``); the slug is
 * parsed from ``window.location.pathname`` directly.
 */

import "@/assets/theme.css";
import "@/public_shared/forms.css";
import { mountApp } from "@/lib/mount";
import PublicForm from "./PublicForm.svelte";

mountApp(PublicForm);
