import { defineConfig } from "@playwright/test";

/**
 * Playwright runs the critical-path scenario against a fresh dev
 * stack: backend + frontend dev server, both spun up by the
 * ``webServer`` block. Start commands assume the project is set up
 * locally (uv + npm both available).
 *
 * Required env when running:
 *   JWT_SECRET, EMAIL_ENCRYPTION_KEY  (any test-grade values)
 *   LOCAL_MODE=1                      seeds admin / organiser
 *
 * Port overrides (optional — defaults match the dev workflow):
 *   E2E_API_PORT       backend port (default 8000)
 *   E2E_FRONTEND_PORT  vite port    (default 5173)
 * Set both when something else is already on the defaults so the
 * test stack doesn't collide with an unrelated dev server.
 *
 * The API binary doesn't import a scheduler (audit #8); the worker
 * container handles hourly sweeps in production. E2E doesn't need
 * the worker to be up.
 */
const API_PORT = process.env.E2E_API_PORT ?? "8000";
const FRONTEND_PORT = process.env.E2E_FRONTEND_PORT ?? "5173";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false, // share one DB
  retries: 0,
  reporter: "list",
  use: {
    baseURL: `http://localhost:${FRONTEND_PORT}`,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  webServer: [
    {
      // Playwright spawns webServer commands via /bin/sh, which has
      // no ``source`` builtin — use POSIX ``.`` instead. The
      // ``[ -f .env ] &&`` guard lets CI run with no .env file (env
      // comes from the job-level env: block) without erroring.
      command: `cd .. && set -a && [ -f .env ] && . ./.env; set +a; export LOCAL_MODE=1 && uv run uvicorn backend.main:app --port ${API_PORT}`,
      url: `http://localhost:${API_PORT}/health`,
      timeout: 30_000,
      reuseExistingServer: !process.env.CI,
    },
    {
      command: `npm run dev -- --port ${FRONTEND_PORT} --strictPort`,
      url: `http://localhost:${FRONTEND_PORT}`,
      timeout: 30_000,
      reuseExistingServer: !process.env.CI,
    },
  ],
  projects: [
    { name: "chromium", use: { browserName: "chromium" } },
  ],
});
