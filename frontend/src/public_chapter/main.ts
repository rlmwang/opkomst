/**
 * Public chapter-agenda mini-app entry. Mounts a single component to
 * ``#app``: no router, no Pinia, no Vue Query, no
 * vue-i18n, same lean bundle as the other public pages.
 *
 * Handles one URL shape (``/e/<chapter-slug>``); the slug is parsed from
 * ``window.location.pathname`` directly.
 */

import { mount } from "svelte";
import "@/assets/theme.css";
import "@/public_shared/forms.css";
import PublicChapter from "./PublicChapter.svelte";

mount(PublicChapter, { target: document.getElementById("app")! });
