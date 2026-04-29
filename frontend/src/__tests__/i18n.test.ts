/**
 * The ``usersTitle`` regression: ``t("usersTitle")`` resolved
 * against no value and rendered the literal string. Default
 * vue-i18n behaviour is silent in production — these tests pin
 * the strict missing-key handler we wired in ``src/i18n.ts``,
 * so the same class of bug breaks the build instead.
 */

import { describe, expect, it, vi } from "vitest";
import { i18n } from "@/i18n";

const t = i18n.global.t;

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
    expect(t("auth.login")).not.toMatch(/^\[/);
    expect(t("auth.login")).not.toBe("");
  });
});
