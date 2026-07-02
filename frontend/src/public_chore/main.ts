/**
 * Public chore ("takenrooster") mini-app entry. Mounts one component to
 * ``#app`` — no router, no Pinia, no Vue Query, no vue-i18n. Unlike the
 * other mini-apps it does register PrimeVue: the time-off editor uses the
 * shared ``DatePicker`` so its date fields are identical to the admin
 * roster form (only that one component is bundled, tree-shaken).
 *
 * Handles ``/c/<slug>`` (enrol) and ``/c/<slug>?s=<token>`` (personal
 * page); both are parsed from the URL inside the component.
 */

import PrimeVue from "primevue/config";
import { createApp } from "vue";
import { primeVueConfig } from "@/primevue-preset";
import "@/assets/theme.css";
import "@/public_shared/forms.css";
import PublicChore from "./PublicChore.vue";

createApp(PublicChore).use(PrimeVue, primeVueConfig).mount("#app");
