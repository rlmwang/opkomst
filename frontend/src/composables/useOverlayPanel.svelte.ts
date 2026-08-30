import { onMount, tick } from "svelte";

import { type PlacementOptions, placePanel } from "./overlay-panel";

/**
 * A panel that opens against a field and is moved to the body.
 *
 * The Svelte half of ``useOverlayPanel``: same four behaviours, same
 * placement arithmetic (``./overlay-panel``), different reactivity.
 *
 * * Positioned against the viewport rather than the anchor's parent.
 * * Flipped above the field when there is no room below it.
 * * Closed by a pointer press anywhere else, caught in the capture phase
 *   so a button underneath does not act on the press that was only
 *   meant to dismiss.
 * * Closed by Escape, with focus handed back to whatever opened it.
 *
 * ``onEscape`` says where focus goes; without one it goes to the anchor,
 * which is right whenever the anchor is the thing the user was on.
 */

/**
 * What the panel wears between rendering and being measured.
 *
 * It has to be out of the document's flow from the very first frame.
 * The panel is moved to the end of ``<body>``, so with no ``position``
 * it is laid out there, at the bottom of the page: the document grows
 * by its height, and a panel that takes focus, which the ones with a
 * filter box do, is scrolled into view by the browser. That is a jump
 * of about a screen, and putting the real placement on a frame later
 * does not undo it, because the scroll has already happened.
 *
 * Hidden rather than merely offscreen, so nothing is drawn in the wrong
 * place, and ``visibility`` rather than ``display`` because a panel
 * with no layout has no height to measure.
 */
const UNPLACED: Record<string, string> = {
  position: "absolute",
  top: "0",
  insetInlineStart: "0",
  visibility: "hidden",
};
export function useOverlayPanel(options: PlacementOptions & { onEscape?: () => void } = {}) {
  const { onEscape, ...placement } = options;

  let anchor = $state<HTMLElement | undefined>();
  let panel = $state<HTMLElement | undefined>();
  let open = $state(false);
  let style = $state<Record<string, string>>(UNPLACED);
  let flipped = $state(false);

  function place(): void {
    if (!anchor || !panel) return;
    const next = placePanel(anchor, panel, placement);
    style = next.style;
    flipped = next.flipped;
  }

  function show(target?: HTMLElement): void {
    if (open) return;
    if (target) anchor = target;
    // Re-armed for this opening: the last one left its own placement
    // behind, and the field may have moved since.
    style = UNPLACED;
    open = true;
    // The panel has no size until it has rendered, and its height is
    // what decides whether it opens upward. ``tick`` rather than a
    // frame: it resolves once the DOM is updated and before the browser
    // paints, so the panel is never drawn unplaced.
    void tick().then(place);
  }

  function hide(): void {
    open = false;
  }

  function toggle(target?: HTMLElement): void {
    if (open) hide();
    else show(target);
  }

  function onPointerDown(event: PointerEvent): void {
    if (!open) return;
    const target = event.target as Node;
    if (anchor?.contains(target) || panel?.contains(target)) return;
    hide();
  }

  function onEscapeKey(event: KeyboardEvent): void {
    if (!open || event.key !== "Escape") return;
    event.preventDefault();
    hide();
    if (onEscape) onEscape();
    else anchor?.focus({ preventScroll: true });
  }

  onMount(() => {
    document.addEventListener("pointerdown", onPointerDown, true);
    document.addEventListener("keydown", onEscapeKey, true);
    window.addEventListener("resize", place);
    window.addEventListener("scroll", place, true);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown, true);
      document.removeEventListener("keydown", onEscapeKey, true);
      window.removeEventListener("resize", place);
      window.removeEventListener("scroll", place, true);
    };
  });

  // Getters, because a plain property would hand the caller the value
  // this ran with rather than the one it has.
  return {
    get anchor() {
      return anchor;
    },
    set anchor(el: HTMLElement | undefined) {
      anchor = el;
    },
    get panel() {
      return panel;
    },
    set panel(el: HTMLElement | undefined) {
      panel = el;
    },
    get open() {
      return open;
    },
    get style() {
      return style;
    },
    get flipped() {
      return flipped;
    },
    show,
    hide,
    toggle,
    place,
  };
}
