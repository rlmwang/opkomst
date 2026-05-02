import * as Sentry from "@sentry/vue";
import { QueryClient, VueQueryPlugin } from "@tanstack/vue-query";
import { createPinia } from "pinia";
import { definePreset } from "@primeuix/themes";
import Aura from "@primeuix/themes/aura";
import PrimeVue from "primevue/config";
import ConfirmationService from "primevue/confirmationservice";
import Tooltip from "primevue/tooltip";
import ToastService from "primevue/toastservice";
import { createApp } from "vue";
import { ApiError } from "@/api/client";
import App from "./App.vue";
import { i18n } from "./i18n";
import router from "./router";
import "primeicons/primeicons.css";
import "./assets/theme.css";

// Brand palette anchored at primary.500 (#9f000b) and a warm-cream
// surface scale that matches the app's hand-rolled --brand-bg /
// --brand-surface / --brand-border tokens. Because every PrimeVue
// component (Dialog, Select, AutoComplete, Card, etc.) reads from
// these same surface shades, the dialogs end up exactly the same
// cream as the rest of the app — no separate CSS overrides needed.
const OpkomstPreset = definePreset(Aura, {
  components: {
    // Aura's default off-state track is `{surface.300}`, which maps to
    // our warm-khaki cream and reads as olive-green next to the page
    // background. Anchor off/on/handle to brand-friendly tones: pale-
    // cream track when off, brand-red track when on, cream handle in
    // both states.
    toast: {
      // All three severities anchored on the brand palette so toasts
      // read as one coherent family on the cream background. Success
      // and error share the brand-red palette (Aura's defaults are
      // off-brand green and bright red); they're distinguished by the
      // built-in severity icons (check vs exclamation). Warn keeps a
      // warm amber/sand that harmonises with the cream surfaces
      // instead of Aura's screaming yellow.
      colorScheme: {
        light: {
          success: {
            background: "color-mix(in srgb, {primary.50}, transparent 5%)",
            borderColor: "{primary.200}",
            color: "{primary.600}",
            detailColor: "{surface.700}",
            shadow: "0px 4px 8px 0px color-mix(in srgb, {primary.500}, transparent 96%)",
            closeButton: {
              hoverBackground: "{primary.100}",
              focusRing: { color: "{primary.600}", shadow: "none" },
            },
          },
          error: {
            background: "color-mix(in srgb, {primary.50}, transparent 5%)",
            borderColor: "{primary.200}",
            color: "{primary.600}",
            detailColor: "{surface.700}",
            shadow: "0px 4px 8px 0px color-mix(in srgb, {primary.500}, transparent 96%)",
            closeButton: {
              hoverBackground: "{primary.100}",
              focusRing: { color: "{primary.600}", shadow: "none" },
            },
          },
          warn: {
            background: "color-mix(in srgb, #fff5e2, transparent 5%)",
            borderColor: "#ead9b3",
            color: "#7a5b00",
            detailColor: "{surface.700}",
            shadow: "0px 4px 8px 0px color-mix(in srgb, #b58a1a, transparent 96%)",
            closeButton: {
              hoverBackground: "#f6e4b8",
              focusRing: { color: "#7a5b00", shadow: "none" },
            },
          },
        },
      },
    },
    toggleswitch: {
      colorScheme: {
        light: {
          root: {
            background: "{surface.200}",
            hoverBackground: "{surface.300}",
            checkedBackground: "{primary.color}",
            checkedHoverBackground: "{primary.hover.color}",
            borderColor: "{surface.300}",
            hoverBorderColor: "{surface.400}",
            checkedBorderColor: "{primary.color}",
            checkedHoverBorderColor: "{primary.hover.color}",
          },
          handle: {
            background: "{surface.0}",
            hoverBackground: "{surface.0}",
            checkedBackground: "{surface.0}",
            checkedHoverBackground: "{surface.0}",
            color: "{text.muted.color}",
            hoverColor: "{text.color}",
            checkedColor: "{primary.color}",
            checkedHoverColor: "{primary.hover.color}",
          },
        },
      },
    },
  },
  semantic: {
    // Aura's default ``disabledOpacity: 0.6`` is too subtle on a
    // cream background — disabled icon-buttons read as "almost
    // active". Drop to 0.4 so the distinction is unambiguous on
    // the row's pencil/trash glyphs in particular.
    disabledOpacity: "0.4",
    primary: {
      50: "#fdf2f2",
      100: "#fbdadc",
      200: "#f5b0b4",
      300: "#ec7e85",
      400: "#dc4954",
      500: "#9f000b",
      600: "#8b000a",
      700: "#760008",
      800: "#5e0007",
      900: "#440005",
      950: "#2b0003",
    },
    colorScheme: {
      light: {
        // Surface scale — drives card / dialog / dropdown / input
        // backgrounds, borders, and muted text. 0 + 50 are the lightest
        // (card / dialog body), 200 is the warm border, 600 is muted
        // text, 900 is the body text. Kept warm-but-restrained so the
        // brand red stays the only saturated colour on screen.
        surface: {
          0: "#fbf7ee",
          50: "#f6f1e7",
          100: "#ece4d0",
          200: "#dcd2b9",
          300: "#c4b89b",
          400: "#a59882",
          500: "#7e7466",
          600: "#5e5a52",
          700: "#403d39",
          800: "#28261f",
          900: "#1a1a1a",
          950: "#0d0d0a",
        },
        formField: {
          // Form fields render on the card surface; bumping their
          // own background to surface.0 keeps them visually flush
          // with the card behind them.
          background: "{surface.0}",
          // Aura's default ``disabledBackground = {surface.200}``
          // is the warm-khaki tone our brand palette assigns at
          // that step — reads as olive/brown on a cream page. Use
          // ``{surface.50}`` instead: a barely-darker cream that
          // distinguishes disabled from enabled without
          // introducing a new colour into the surface family.
          disabledBackground: "{surface.50}",
          disabledColor: "{surface.500}",
          borderColor: "{surface.200}",
          color: "{surface.900}",
          placeholderColor: "{surface.500}",
        },
      },
    },
  },
});

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
app.use(PrimeVue, {
  theme: {
    preset: OpkomstPreset,
    options: {
      // Disable automatic dark mode — the app's own surface colors are
      // hard-coded light, so following the OS preference produces an
      // inconsistent half-dark / half-light render.
      darkModeSelector: ".app-dark-never-applied",
      cssLayer: { name: "primevue", order: "primevue, app" },
    },
  },
});
app.use(ToastService);
app.use(ConfirmationService);
app.directive("tooltip", Tooltip);

app.mount("#app");
