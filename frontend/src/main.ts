import { createPinia } from "pinia";
import Aura from "@primeuix/themes/aura";
import PrimeVue from "primevue/config";
import ToastService from "primevue/toastservice";
import { createApp } from "vue";
import App from "./App.vue";
import router from "./router";
import "primeicons/primeicons.css";
import "./assets/theme.css";

const app = createApp(App);

app.use(createPinia());
app.use(router);
app.use(PrimeVue, {
  theme: {
    preset: Aura,
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

app.mount("#app");
