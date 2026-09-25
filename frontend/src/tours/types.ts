import type { AnchorName } from "./anchors.svelte";

/**
 * A tour is data (``docs/design-tour.md`` chapter 5): a list of
 * controls by name and a rule for advancing each. No selectors, no
 * callbacks, no markup. The words live in the locale files by tour,
 * product and position.
 */

export type TourId = "inloggen" | "welkom" | "lijst" | "details" | "formulier" | "beheer";

export type Advance =
  /** A button in the callout. */
  | { kind: "next" }
  /** The control in the hole is pressed. */
  | { kind: "click" }
  /** A named control appears, on this page or the next. */
  | { kind: "until"; name: AnchorName };

export interface Step {
  /** A path pattern in the router's grammar. Absent on a per-page
   *  tour: the step runs on the page the tour was started from. */
  page?: string;
  anchor: AnchorName;
  advance: Advance;
}

/** A step as the store holds it: with its declared position, which is
 *  what its words are keyed by, whatever was dropped around it. */
export interface ResolvedStep extends Step {
  n: number;
}

export interface Tour {
  id: TourId;
  /** A per-page tour resolves its list when it starts, dropping steps
   *  whose control is absent. The two that cross pages keep theirs. */
  perPage: boolean;
  steps: Step[];
}
