import * as Sentry from "@sentry/vue";
import { QueryClient, VueQueryPlugin } from "@tanstack/vue-query";
import { createPinia } from "pinia";
import PrimeVue from "primevue/config";
import ConfirmationService from "primevue/confirmationservice";
import Tooltip from "primevue/tooltip";
import ToastService from "primevue/toastservice";
import { createApp } from "vue";
import { ApiError } from "@/api/client";
import App from "./App.vue";
import { i18n } from "./i18n";
import { primeVueConfig } from "./primevue-preset";
import router from "./router";
import "primeicons/primeicons.css";
import "./assets/theme.css";
import "./assets/forms.css";

const app = createApp(App);

// Sentry. The DSN is injected at build time via
// ``VITE_SENTRY_DSN``; left unset in dev (``import.meta.env.DEV``)
// so a noisy ``console`` doesn't spam during local work. PII is
// off — usernames, IPs, and request bodies are not captured. The
// app's own ``app.config.errorHandler`` is replaced by Sentry's,
// so a render error or unhandled promise reaches the same DSN as
// backend exceptions.
const sentryDsn = import.meta.env.VITE_SENTRY_DSN;
if (sentryDsn && !import.meta.env.DEV) {
  Sentry.init({
    app,
    dsn: sentryDsn,
    environment: import.meta.env.VITE_SENTRY_ENVIRONMENT || "production",
    sendDefaultPii: false,
    // Lower the trace sample rate to zero by default — opkomst
    // gets little traffic and tracing every event would burn
    // the free-tier quota fast. Bump in env if you want spans.
    tracesSampleRate: Number(
      import.meta.env.VITE_SENTRY_TRACES_SAMPLE_RATE ?? 0,
    ),
  });
}

app.use(createPinia());

// Vue Query owns server state. Defaults: 60 s stale-time so a
// dialog opening from a list (and same-list navigation roundtrips)
// doesn't refetch on mount; retry only on transient (network /
// 5xx) errors — never on 4xx, which by definition won't become
// 2xx in the next second and only delays surfacing the real error
// (e.g. a deleted-event slug page sat on "Loading…" for ~1 s
// before showing "not found"); no refetch-on-window-focus
// (organiser browser tabs sit open all afternoon — refetching
// every focus would be noisy without solving anything real).
// Per-key composables override staleTime where the data is
// rarer-change (chapters, users) or stricter (mutations always
// invalidate so a slightly longer stale window doesn't cause
// divergence).
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

app.use(i18n);
app.use(router);
app.use(PrimeVue, primeVueConfig);
app.use(ToastService);
app.use(ConfirmationService);
app.directive("tooltip", Tooltip);

app.mount("#app");
