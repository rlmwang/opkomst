/**
 * Where an overlay panel goes, as arithmetic.
 *
 * Split out of ``useOverlayPanel`` when the front end started moving to
 * Svelte (``docs/tasks/svelte``): the date picker is rendered by both
 * halves of the app for the length of the migration, so the placement
 * rules are written once and each half wraps them in its own reactivity.
 */

export interface PlacementOptions {
  /** Make the panel at least as wide as the field it hangs under, which
   *  is what a list wants and a popover does not. */
  matchAnchorWidth?: boolean;
  /** The gap between the anchor and the panel. Only the popover asks. */
  gutter?: number;
}

export interface Placement {
  style: Record<string, string>;
  /** True when the panel sits above its anchor rather than below it. */
  flipped: boolean;
}

/**
 * Positioned against the viewport rather than the anchor's parent,
 * because a panel rendered inside a form is clipped by any card that
 * hides its overflow. Flipped above the field when there is no room
 * below it, and kept inside the viewport horizontally, because a menu
 * hanging off a button near the right edge would otherwise run past it.
 */
export function placePanel(
  anchor: HTMLElement,
  panel: HTMLElement,
  { matchAnchorWidth = true, gutter = 0 }: PlacementOptions = {},
): Placement {
  const rect = anchor.getBoundingClientRect();
  const height = panel.offsetHeight;
  const width = panel.offsetWidth;
  const below = window.innerHeight - rect.bottom;
  const flipped = below < height + gutter + 8 && rect.top > height + gutter + 8;
  const left = Math.max(8, Math.min(rect.left, window.innerWidth - width - 8));
  return {
    flipped,
    style: {
      position: "absolute",
      insetInlineStart: `${left + window.scrollX}px`,
      top: `${(flipped ? rect.top - height - gutter : rect.bottom + gutter) + window.scrollY}px`,
      ...(matchAnchorWidth ? { minWidth: `${rect.width}px` } : {}),
    },
  };
}
