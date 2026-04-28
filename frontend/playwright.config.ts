import { defineConfig } from "@playwright/test";

/**
 * Playwright runs the critical-path scenario against a fresh dev
 * stack: backend on 8000, frontend dev server on 5173. Both are
 * spun up by the ``webServer`` block — start commands assume the
 * project is set up locally (uv + npm both available).
 *
 * Required env when running:
 *   JWT_SECRET, EMAIL_ENCRYPTION_KEY  (any test-grade values)
 *   LOCAL_MODE=1                      seeds admin / organiser
 *
 * The API binary doesn't import a scheduler (audit #8); the worker
 * container handles hourly sweeps in production. E2E doesn't need
 * the worker to be up.
 */
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false, // share one DB
  retries: 0,
  reporter: "list",
  use: {
    baseURL: "http://localhost:5173",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  webServer: [
    {
      command: "cd .. && set -a && source .env && set +a && export LOCAL_MODE=1 && uv run uvicorn backend.main:app --port 8000",
      url: "http://localhost:8000/health",
      timeout: 30_000,
      reuseExistingServer: !process.env.CI,
    },
    {
      command: "npm run dev",
      url: "http://localhost:5173",
      timeout: 30_000,
      reuseExistingServer: !process.env.CI,
    },
  ],
  projects: [
    { name: "chromium", use: { browserName: "chromium" } },
  ],
});
