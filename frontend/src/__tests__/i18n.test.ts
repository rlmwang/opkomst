/**
 * The ``usersTitle`` regression: ``t("usersTitle")`` resolved against no
 * value and rendered the literal string. vue-i18n was silent about that
 * in production, and these tests pin the strict handler in
 * ``lib/i18n-core`` that replaced its silence. They outlived vue-i18n
 * itself, and Vue, which is the point of them.
 */

import { beforeAll, describe, expect, it, vi } from "vitest";
import { initI18n, locale, setLocale, t } from "@/i18n.svelte";

// The catalogues are fetched rather than bundled, so the active one has
// to be loaded before any lookup resolves.
beforeAll(async () => {
  await initI18n();
});

describe("i18n missing-key handler", () => {
  it("returns ``[key]`` for missing keys so the UI surfaces the gap visibly", () => {
    const out = t("definitely.not.a.real.key");
    // Visually-obvious bracket-wrap, *not* the bare key (which
    // would blend into normal copy).
    expect(out).toBe("[definitely.not.a.real.key]");
  });

  it("warns on the console (dev) for an unknown key", () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    t("another.missing.key");
    expect(warn).toHaveBeenCalled();
    warn.mockRestore();
  });

  it("dedupes repeated misses on the same key (no warn-storm)", () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    t("dedupe.me");
    t("dedupe.me");
    t("dedupe.me");
    // The handler tracks ``${locale}:${key}`` in a Set; the
    // second + third hit don't re-warn.
    expect(warn).toHaveBeenCalledTimes(1);
    warn.mockRestore();
  });

  it("known keys still resolve to the actual translation", () => {
    // Sanity: the strict handler doesn't break normal lookups.
    expect(t("auth.sendLink")).not.toMatch(/^\[/);
    expect(t("auth.sendLink")).not.toBe("");
  });
});

describe("lazy catalogues", () => {
  it("has the active language after init, and resolves real copy from it", () => {
    expect(locale()).toBe("nl");
    expect(t("auth.sendLink")).not.toMatch(/^\[/);
  });

  it("fetches the other language on switch, then renders it", async () => {
    const dutch = t("auth.sendLink");
    await setLocale("en");
    expect(locale()).toBe("en");
    const english = t("auth.sendLink");
    expect(english).not.toMatch(/^\[/);
    expect(english).not.toBe(dutch);
    await setLocale("nl");
    expect(t("auth.sendLink")).toBe(dutch);
  });
});
