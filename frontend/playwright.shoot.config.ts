import { defineConfig } from "@playwright/test";

import base from "./playwright.config";

/**
 * The manual's shooting script (``e2e/shoot-manual.ts``), run by
 * ``make shoot-manual`` and never by ``playwright test``: it writes
 * pictures into the repository rather than proving anything. Same dev
 * stack as the specs, one worker, because it signs in as the same
 * accounts the specs use and drives the tour one step at a time.
 */
export default defineConfig({
  ...base,
  testMatch: /shoot-manual\.ts$/,
  workers: 1,
  timeout: 300_000,
  projects: [{ name: "chromium", use: { browserName: "chromium" } }],
});
