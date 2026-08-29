import { createApp } from "vue";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// Sentry is fetched after the app mounts, which leaves a window at
// startup with nothing listening. These pin the buffer that covers it:
// a crash while the app is booting is exactly the crash worth hearing
// about, so it has to survive until the reporter arrives.

const init = vi.fn();
const captureMessage = vi.fn();
const captureException = vi.fn();
vi.mock("@/lib/sentry-client", () => ({ init, captureMessage, captureException }));

let sentry: typeof import("@/lib/sentry");

beforeEach(async () => {
  vi.resetModules();
  init.mockClear();
  captureMessage.mockClear();
  captureException.mockClear();
  vi.stubEnv("DEV", false);
  vi.stubEnv("VITE_SENTRY_DSN", "https://key@example.invalid/1");
  sentry = await import("@/lib/sentry");
});

afterEach(() => {
  vi.unstubAllEnvs();
});

const app = () => createApp({ render: () => null });

describe("before Sentry has loaded", () => {
  it("holds reports rather than dropping them", async () => {
    sentry.captureMessage("missing key", "warning");
    sentry.captureError(new Error("boom"));
    expect(captureMessage).not.toHaveBeenCalled();

    await sentry.start(app());

    expect(captureMessage).toHaveBeenCalledWith("missing key", "warning");
    expect(captureException).toHaveBeenCalledWith(expect.objectContaining({ message: "boom" }));
  });

  it("catches what Vue throws during mount", async () => {
    const a = app();
    sentry.arm(a);
    a.config.errorHandler?.(new Error("render failed"), null, "");
    await sentry.start(a);
    expect(captureException).toHaveBeenCalledWith(expect.objectContaining({ message: "render failed" }));
  });

  it("stops buffering once it is full, so a boot loop cannot grow it", async () => {
    for (let i = 0; i < 120; i++) sentry.captureMessage(`m${i}`, "warning");
    await sentry.start(app());
    expect(captureMessage).toHaveBeenCalledTimes(50);
  });
});

describe("once Sentry has loaded", () => {
  it("reports straight through instead of buffering", async () => {
    await sentry.start(app());
    sentry.captureMessage("later", "warning");
    expect(captureMessage).toHaveBeenCalledWith("later", "warning");
  });

  it("hands its global listeners over, so nothing is counted twice", async () => {
    const a = app();
    sentry.arm(a);
    await sentry.start(a);
    captureException.mockClear();
    window.dispatchEvent(new ErrorEvent("error", { error: new Error("after handover") }));
    // Sentry installs its own handlers in init; ours are gone.
    expect(captureException).not.toHaveBeenCalled();
  });
});

describe("without a DSN", () => {
  it("does not fetch Sentry at all", async () => {
    vi.stubEnv("VITE_SENTRY_DSN", "");
    vi.resetModules();
    const fresh = await import("@/lib/sentry");
    await fresh.start(app());
    expect(init).not.toHaveBeenCalled();
  });
});
