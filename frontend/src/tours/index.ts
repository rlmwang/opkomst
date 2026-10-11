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

/** The manual's chapter for the page at ``path``, by number
 *  (``docs/design-manual.md`` chapter 9), or nothing for the index. */
export function manualChapterFor(path: string): number | null {
  if (path === "/users") return 13;
  if (path === "/chapters" || path === "/settings") return 12;
  const found = compile("/:product/*").re.exec(path) ?? compile("/:product").re.exec(path);
  if (!found) return null;
  const product = found[1] as Product;
  if (!PRODUCTS.includes(product)) return null;
  if (path.endsWith("/archived")) return 10;
  if (product === "event") return path.endsWith("/details") ? 3 : 2;
  return { datepoll: 5, chore: 6, form: 7, quiz: 8, compass: 9 }[product];
}

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
