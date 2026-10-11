/**
 * The hole and the mask, as arithmetic, so a test can check them
 * without a browser painting anything.
 */

export interface Hole {
  x: number;
  y: number;
  w: number;
  h: number;
  /** The corner radius, read off the control it holds. */
  r: number;
}

export interface Viewport {
  w: number;
  h: number;
}

/** The control's box plus ``pad`` on each side, with the radius of what
 *  it holds: a card's 10px, a button's 6px, a pill's full round. Read
 *  off the computed style so the hole never guesses. */
export function holeGeometry(el: HTMLElement, pad: number): Hole {
  const rect = el.getBoundingClientRect();
  const radius = parseFloat(getComputedStyle(el).borderTopLeftRadius) || 0;
  const w = rect.width + pad * 2;
  const h = rect.height + pad * 2;
  // A pill's 999px means "as round as it can be", which is half the
  // shorter side; anything else is what it says, kept inside the box.
  const r = Math.min(radius + pad, w / 2, h / 2);
  return { x: rect.left - pad, y: rect.top - pad, w, h, r };
}

/** The viewport minus a rounded rectangle, for an even-odd fill. */
export function maskPath(viewport: Viewport, hole: Hole): string {
  const { x, y, w, h, r } = hole;
  const outer = `M0 0H${viewport.w}V${viewport.h}H0Z`;
  const inner =
    `M${x + r} ${y}` +
    `H${x + w - r}` +
    `A${r} ${r} 0 0 1 ${x + w} ${y + r}` +
    `V${y + h - r}` +
    `A${r} ${r} 0 0 1 ${x + w - r} ${y + h}` +
    `H${x + r}` +
    `A${r} ${r} 0 0 1 ${x} ${y + h - r}` +
    `V${y + r}` +
    `A${r} ${r} 0 0 1 ${x + r} ${y}` +
    `Z`;
  return `${outer} ${inner}`;
}

/** Whether the callout is a sheet across the bottom rather than a
 *  popover: on a phone, and wherever the hole is taller than 60% of
 *  the viewport, which is the form step. */
export function calloutSheet(viewport: Viewport, hole: Hole): boolean {
  return viewport.w <= 480 || hole.h > viewport.h * 0.6;
}
