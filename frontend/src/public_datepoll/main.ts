/**
 * Public datepoll mini-app entry. Mounts a single component to
 * ``#app``: no router, no Pinia, no Vue Query, no
 * vue-i18n. Mirrors ``src/public_form/main.ts`` one-to-one; same
 * wire-weight target.
 *
 * Handles exactly one URL shape (``/d/<slug>``); the slug is parsed
 * from ``window.location.pathname`` inside the component.
 */

import "@/assets/theme.css";
import "@/public_shared/forms.css";
import { mountPublic } from "@/public_shared/mount";
import PublicDatepoll from "./PublicDatepoll.svelte";

mountPublic(PublicDatepoll);
