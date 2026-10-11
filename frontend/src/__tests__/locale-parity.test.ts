/**
 * The two catalogues carry the same keys. A key one language lacks
 * falls back to Dutch at runtime, which is a Dutch sentence on an
 * English screen and nothing in the console to say so.
 */
import { describe, expect, it } from "vitest";

import en from "@/locales/en.json";
import nl from "@/locales/nl.json";

type Node = string | { [key: string]: Node };

function flatten(node: Node, prefix = ""): string[] {
  if (typeof node === "string") return [prefix];
  return Object.entries(node).flatMap(([k, v]) => flatten(v, prefix ? `${prefix}.${k}` : k));
}

describe("locale parity", () => {
  it("nl and en have exactly the same keys", () => {
    const a = flatten(nl as Node).sort();
    const b = flatten(en as Node).sort();
    expect(b.filter((k) => !a.includes(k)), "keys only in en").toEqual([]);
    expect(a.filter((k) => !b.includes(k)), "keys only in nl").toEqual([]);
  });
});
