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

// Brand red — anchored at primary.500 (#9f000b). The lighter shades are
// the natural pink tints of the same hue; the darker shades are used
// for hover/active states on buttons and other interactive elements.
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
  },
  // Secondary button tones live in theme.css (CSS overrides — the
  // PrimeVue TS types don't expose the secondary tokens at this level).
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
