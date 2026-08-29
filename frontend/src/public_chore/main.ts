/**
 * Public chore ("takenrooster") mini-app entry. Mounts one component to
 * ``#app`` — no router, no Pinia, no Vue Query, no vue-i18n, and since
 * the time-off editor's date fields became the app's own ``DatePicker``,
 * no PrimeVue either.
 *
 * Handles ``/c/<slug>`` (enrol) and ``/c/<slug>?s=<token>`` (personal
 * page); both are parsed from the URL inside the component.
 */

import { createApp } from "vue";
import "@/assets/theme.css";
import "@/public_shared/forms.css";
import PublicChore from "./PublicChore.vue";

createApp(PublicChore).mount("#app");
