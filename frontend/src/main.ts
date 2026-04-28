import { QueryClient, VueQueryPlugin } from "@tanstack/vue-query";
import { createPinia } from "pinia";
import { definePreset } from "@primeuix/themes";
import Aura from "@primeuix/themes/aura";
import PrimeVue from "primevue/config";
import ConfirmationService from "primevue/confirmationservice";
import Tooltip from "primevue/tooltip";
import ToastService from "primevue/toastservice";
import { createApp } from "vue";
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
          borderColor: "{surface.200}",
          color: "{surface.900}",
          placeholderColor: "{surface.500}",
        },
      },
    },
  },
});

const app = createApp(App);

app.use(createPinia());

// Vue Query owns server state. Defaults: 30 s stale-time so a
// dialog opening from a list doesn't refetch on mount; one retry
// for a transient API hiccup; no refetch-on-window-focus
// (organiser browser tabs sit open all afternoon — refetching
// every focus would be noisy without solving anything real).
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: 1,
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
