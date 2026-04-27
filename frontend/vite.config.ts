/// <reference types="vitest" />
import { fileURLToPath, URL } from "node:url";
import vue from "@vitejs/plugin-vue";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [vue()],
  test: {
    environment: "node",
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
      "/api": "http://localhost:8000",
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
