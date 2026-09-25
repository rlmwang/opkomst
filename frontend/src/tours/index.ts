import { compile } from "@/router/router.svelte";
import type { TourId } from "./types";

/**
 * Which tour the menu offers on which family of pages
 * (``docs/design-tour.md`` chapter 9). The product is the route's
 * resource segment, so the words can name it.
 */

export const PRODUCTS = ["event", "datepoll", "chore", "form", "quiz", "compass"] as const;
export type Product = (typeof PRODUCTS)[number];

export interface Offer {
  id: TourId;
  product: Product | null;
}

const FAMILIES: ReadonlyArray<{ pattern: string; id: TourId }> = [
  { pattern: "/:product", id: "lijst" },
  { pattern: "/:product/archived", id: "lijst" },
  { pattern: "/:product/new", id: "formulier" },
  { pattern: "/:product/:id/edit", id: "formulier" },
  { pattern: "/:product/:id/details", id: "details" },
];

const ADMIN = ["/users", "/chapters", "/settings"];

/** The tour for the page at ``path``, or nothing when the page has none. */
export function tourFor(path: string): Offer | null {
  if (ADMIN.includes(path)) return { id: "beheer", product: null };
  for (const { pattern, id } of FAMILIES) {
    const { re } = compile(pattern);
    const found = re.exec(path);
    if (!found) continue;
    const product = found[1] as Product;
    if (!PRODUCTS.includes(product)) return null;
    return { id, product };
  }
  return null;
}
