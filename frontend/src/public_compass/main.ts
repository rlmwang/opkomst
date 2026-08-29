/**
 * Public kompas mini-app entry. Mounts one component to ``#app`` — no
 * router, no Pinia, no Vue Query, no vue-i18n, the same
 * wire-weight target as the other five.
 *
 * Handles one URL shape (``/k/<slug>``); the slug is parsed from
 * ``window.location.pathname`` directly.
 */

import "@/assets/theme.css";
import "@/public_shared/forms.css";
import { mountPublic } from "@/public_shared/mount";
import PublicCompass from "./PublicCompass.svelte";

mountPublic(PublicCompass);
