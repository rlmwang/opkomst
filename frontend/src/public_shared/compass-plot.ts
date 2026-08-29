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

export interface PlotPoint {
  name?: string | null;
  x: number;
  y: number;
  you?: boolean;
}

export interface Cluster {
  x: number;
  y: number;
  names: string[];
  count: number;
  you: boolean;
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

/** Submissions at the same coordinate are one dot. Keyed on the rounded
 *  pair the server already rounded, so two identical answer sets always
 *  land in the same cluster. The reader's own dot comes last, so it
 *  draws on top of the room. */
export function clusterPoints(points: PlotPoint[], anonymousLabel: string): Cluster[] {
  const bySpot = new Map<string, Cluster>();
  for (const point of points) {
    const key = `${point.x}:${point.y}`;
    const found = bySpot.get(key);
    const name = point.name ?? anonymousLabel;
    if (found) {
      found.names.push(name);
      found.count += 1;
      found.you = found.you || Boolean(point.you);
    } else {
      bySpot.set(key, { x: point.x, y: point.y, names: [name], count: 1, you: Boolean(point.you) });
    }
  }
  return [...bySpot.values()].sort((a, b) => Number(a.you) - Number(b.you));
}

/** Radius grows with the count and stops growing: a cluster of forty
 *  should read as bigger than one of four and still be a dot. */
export function radius(cluster: Cluster): number {
  return 2.2 + Math.min(2.8, Math.sqrt(cluster.count - 1) * 1.1);
}

export function label(cluster: Cluster): string {
  return cluster.names.join(", ");
}
