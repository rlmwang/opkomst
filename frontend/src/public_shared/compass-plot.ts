/**
 * The map's arithmetic, without the drawing: the box, the projection
 * and the clustering.
 *
 * Split out of ``CompassPlot`` when the front end started moving to
 * Svelte (``docs/tasks/svelte``), because for a while the same picture
 * is drawn twice, by the organiser's Vue component and by the
 * respondent's Svelte one, and two copies of a clustering rule is two
 * copies that drift. The reasoning behind the rules lives with the
 * components; this is what they both run.
 */

/** The two shapes the plot reads, declared here rather than imported
 *  from the generated schema: the mini-app bundles do not pull
 *  ``api/types`` in, and a plot needs four numbers and a name. */
export interface PlotAxis {
  axis: string;
  low_name: string;
  high_name: string;
}

/** One dot: where it is, how many people are standing in it, and the
 *  first few of their pseudonyms. Grouped by the database, which knows
 *  the coordinates because it worked them out. */
export interface PlotSpot {
  x: number;
  y: number;
  count: number;
  names: (string | null)[];
  you?: boolean;
}

// The drawing box. The plot area is 100x100 user units with room around
// it for the four side names; the SVG scales to its container.
export const PAD = 22;
export const SIZE = 100;
export const BOX = SIZE + PAD * 2;

/** [-1, 1] to the plot box. */
export function px(value: number): number {
  return PAD + ((value + 1) / 2) * SIZE;
}

/** The same, flipped: the high side of an axis is drawn at the top, and
 *  SVG counts downward. */
export function py(value: number): number {
  return PAD + ((1 - value) / 2) * SIZE;
}

/** The reader's own dot draws last, over the room rather than under
 *  it. Everything else keeps the order it arrived in, which is the
 *  crowded spots first. */
export function drawOrder(spots: PlotSpot[]): PlotSpot[] {
  return [...spots].sort((a, b) => Number(Boolean(a.you)) - Number(Boolean(b.you)));
}

/** Radius grows with the count and stops growing: a dot holding forty
 *  should read as bigger than one holding four and still be a dot. */
export function radius(spot: PlotSpot): number {
  return 2.2 + Math.min(2.8, Math.sqrt(spot.count - 1) * 1.1);
}

/** Who is in this dot. The server sends the first few names of a
 *  crowded one, so the label ends in an ellipsis when there are more
 *  people in the dot than names to show. */
export function label(spot: PlotSpot, anonymousLabel: string): string {
  const shown = spot.names.map((name) => name ?? anonymousLabel).join(", ");
  return spot.count > spot.names.length ? `${shown}, …` : shown;
}
