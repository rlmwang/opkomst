import { VueQueryPlugin } from "@tanstack/vue-query";
import { createPinia } from "pinia";
import { createApp } from "vue";
import { queryClient } from "@/lib/query-client";
import { connectRouter } from "@/lib/router-bridge";
import * as sentry from "@/lib/sentry";
import { tooltip } from "@/lib/tooltip";
import App from "./App.vue";
import { initI18n } from "./i18n";
import router from "./router";
import "./assets/theme.css";
import "./assets/forms.css";

const app = createApp(App);

// Start catching errors now, and fetch Sentry itself once the app is
// on screen (``lib/sentry.ts``). Arming is two listeners and an array;
// the 31 kB that does the reporting is not something an organiser
// should wait behind to see their dashboard.
sentry.arm(app);

app.use(createPinia());

// Vue Query owns server state. The client itself is
// ``lib/query-client``, shared with the Svelte half so both read one
// cache while the app crosses over.
app.use(VueQueryPlugin, { queryClient });

app.use(router);
// The Svelte half reads this same router rather than running its own
// (``lib/router-bridge``), until the route table itself crosses.
connectRouter(router);
app.directive("tooltip", tooltip);

// The active language is fetched, not bundled, so it has to be in hand
// before the first render or every string would paint as ``[key]``. It
// is one small request that starts alongside the entry chunk.
initI18n().then(() => {
  app.mount("#app");
  // After mount on purpose: the download competes with nothing, and
  // anything that went wrong before this point is buffered and replayed
  // the moment it lands.
  void sentry.start(app);
});
