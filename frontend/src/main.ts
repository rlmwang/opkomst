import { QueryClient, VueQueryPlugin } from "@tanstack/vue-query";
import { createPinia } from "pinia";
import { createApp } from "vue";
import { ApiError } from "@/api/client";
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

// Vue Query owns server state. Defaults: 60 s stale-time so a dialog
// opening from a list (and same-list navigation roundtrips) doesn't
// refetch on mount; retry only on transient (network / 5xx) errors,
// never on 4xx, which by definition won't become 2xx in the next second
// and only delays surfacing the real error; no refetch-on-window-focus,
// because organiser tabs sit open all afternoon.
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 60_000,
      retry: (failureCount, error) => {
        if (error instanceof ApiError && error.status >= 400 && error.status < 500) return false;
        return failureCount < 1;
      },
      refetchOnWindowFocus: false,
    },
  },
});
app.use(VueQueryPlugin, { queryClient });

app.use(router);
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
