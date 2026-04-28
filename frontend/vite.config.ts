/// <reference types="vitest" />
import { fileURLToPath, URL } from "node:url";
import vue from "@vitejs/plugin-vue";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [vue()],
  test: {
    // happy-dom for component / Vue-Query composables (need a DOM
    // for ``app.mount(document.createElement(...))``); pure-utility
    // tests that don't touch the DOM are unaffected.
    environment: "happy-dom",
    include: ["src/__tests__/**/*.test.ts"],
  },
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  server: {
    port: 5173,
    proxy: {
      // Forward /api/* to the backend. Defaults to the dev port; the
      // E2E_API_PORT override lets ``playwright test`` boot the backend
      // on a non-default port when 8000 is already in use.
      "/api": `http://localhost:${process.env.E2E_API_PORT ?? "8000"}`,
    },
  },
  build: {
    rollupOptions: {
      output: {
        // Split heavy vendor libs into their own chunks. The main
        // app chunk drops below the 500 kB warning threshold; the
        // vendor chunks cache separately and survive across deploys
        // that touch app code but not deps.
        manualChunks: {
          vue: ["vue", "vue-router", "pinia"],
          i18n: ["vue-i18n"],
          primevue: [
            "primevue/autocomplete",
            "primevue/button",
            "primevue/confirmdialog",
            "primevue/datepicker",
            "primevue/dialog",
            "primevue/iconfield",
            "primevue/inputicon",
            "primevue/inputnumber",
            "primevue/inputtext",
            "primevue/password",
            "primevue/select",
            "primevue/tag",
            "primevue/textarea",
            "primevue/toast",
            "primevue/toggleswitch",
            "primevue/tooltip",
            "primevue/useconfirm",
            "primevue/usetoast",
          ],
        },
      },
    },
  },
});
