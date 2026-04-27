import { describe, expect, it } from "vitest";
import { isValidEmail } from "@/lib/validate";

describe("isValidEmail", () => {
  it("accepts well-formed addresses", () => {
    expect(isValidEmail("alice@example.com")).toBe(true);
    expect(isValidEmail("a.b+tag@example.co.uk")).toBe(true);
  });

  it("rejects malformed addresses", () => {
    expect(isValidEmail("not-an-email")).toBe(false);
    expect(isValidEmail("a@b")).toBe(false);
    expect(isValidEmail("missing@dot")).toBe(false);
    expect(isValidEmail("")).toBe(false);
    expect(isValidEmail(" @ . ")).toBe(false);
  });
});
