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
