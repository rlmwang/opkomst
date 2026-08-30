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

/**
 * Bring a row into view inside its own list, and nowhere else.
 *
 * ``scrollIntoView`` scrolls every scrollable ancestor, the document
 * included, so a panel hanging below the fold took the whole page with
 * it: the list moved by a row and the page moved by a screen. The panel
 * is positioned against the viewport, so scrolling the document is
 * never what this wants.
 */
export function scrollRowIntoView(list: HTMLElement | null | undefined, index: number): void {
  const row = list?.children[index] as HTMLElement | undefined;
  if (!list || !row) return;
  const top = row.offsetTop;
  const bottom = top + row.offsetHeight;
  if (top < list.scrollTop) list.scrollTop = top;
  else if (bottom > list.scrollTop + list.clientHeight) list.scrollTop = bottom - list.clientHeight;
}

/**
 * Move a panel out of the tree it was declared in, so no card with
 * hidden overflow can clip it. Its position is the viewport's already
 * (``placePanel``), so the move changes nothing but the clipping.
 *
 * The body is the destination, except inside a modal. ``AppDialog`` is
 * the browser's ``<dialog>`` opened with ``showModal``, which paints in
 * the top layer: everything in the body renders underneath it, whatever
 * its ``z-index`` says, so a panel sent to the body from a field in a
 * dialog opened below the dialog instead of over it. The dialog is the
 * top layer, so a panel that goes inside it is in the top layer too.
 */
export function portalTarget(anchor: HTMLElement | null | undefined): HTMLElement {
  return anchor?.closest("dialog") ?? document.body;
}
