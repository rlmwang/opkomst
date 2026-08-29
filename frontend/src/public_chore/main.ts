/**
 * Public chore ("takenrooster") mini-app entry. Mounts one component to
 * ``#app``: no router, no Pinia, no Vue Query, no vue-i18n.
 *
 * Handles ``/c/<slug>`` (enrol) and ``/c/<slug>?s=<token>`` (personal
 * page); both are parsed from the URL inside the component.
 */

import "@/assets/theme.css";
import "@/public_shared/forms.css";
import { mountPublic } from "@/public_shared/mount";
import PublicChore from "./PublicChore.svelte";

mountPublic(PublicChore);
