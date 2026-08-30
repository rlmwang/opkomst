<script lang="ts">
import {
  BOX,
  PAD,
  SIZE,
  type PlotAxis,
  type PlotPoint,
  clusterPoints,
  label,
  px,
  py,
  radius,
} from "./compass-plot";

/**
 * The map: one square, two axes, one dot per submission
 * (``docs/design-kompas.md`` 2.4).
 *
 * Two rules the quiz's histogram had to learn the hard way, applied
 * here from the start:
 *
 * **The domain is fixed at [-1, 1].** Not derived from the data, which
 * is what ``../stemwijzer``'s plot does. A map that rescales as people
 * fill it in is a map where your dot moves after you have seen it, and
 * the axis then means something different on every screenshot.
 *
 * **Coincident dots cluster; they do not jitter.** Answer sets repeat,
 * especially on a short kompas. Jitter was the first idea and it is
 * dishonest: it puts a dot where nobody is. Submissions at the same
 * coordinate become one dot whose radius grows with the count, and
 * whose label lists every name in it.
 *
 * Inline SVG, no chart library: two lines, four labels and a handful of
 * circles do not need one, and the public mini-apps have a bundle
 * budget. It carries no i18n of its own for the same reason
 * ``QuestionField`` does: the organiser's page and the respondent's map
 * are the same picture. The two words it needs come in as props.
 *
 * The arithmetic is ``./compass-plot``, shared with the Vue one the
 * organiser's details page renders while the app moves across.
 */
const {
  axes,
  points,
  anonymousLabel,
  ariaLabel,
  compact,
}: {
  axes: PlotAxis[];
  points: PlotPoint[];
  /** What a dot with no pseudonym is called, from the caller's own
   *  string table. */
  anonymousLabel: string;
  /** Names the picture for a screen reader. */
  ariaLabel?: string;
  /** Rendered smaller, without the quadrant tint, when the map is one
   *  card among many rather than the thing the page is about. */
  compact?: boolean;
} = $props();

const xAxis = $derived(axes.find((a) => a.axis === "x") ?? null);
const yAxis = $derived(axes.find((a) => a.axis === "y") ?? null);
const clusters = $derived(clusterPoints(points, anonymousLabel));

// Hover and focus both open the same label, so the map is readable with
// a keyboard and on a phone, where there is no hover at all.
let active = $state<number | null>(null);
</script>

<figure class="compass-plot" class:is-compact={compact}>
  <svg viewBox="0 0 {BOX} {BOX}" role="img" aria-label={ariaLabel}>
    <!-- The four quadrants, tinted so the map reads as four corners
         rather than as a scatter of dots in a box. -->
    {#if !compact}
      <g class="quadrants">
        <rect x={PAD} y={PAD} width={SIZE / 2} height={SIZE / 2} />
        <rect x={PAD + SIZE / 2} y={PAD} width={SIZE / 2} height={SIZE / 2} />
        <rect x={PAD} y={PAD + SIZE / 2} width={SIZE / 2} height={SIZE / 2} />
        <rect x={PAD + SIZE / 2} y={PAD + SIZE / 2} width={SIZE / 2} height={SIZE / 2} />
      </g>
    {/if}

    <rect class="frame" x={PAD} y={PAD} width={SIZE} height={SIZE} />
    <line class="axis-line" x1={PAD} y1={py(0)} x2={PAD + SIZE} y2={py(0)} />
    <line class="axis-line" x1={px(0)} y1={PAD} x2={px(0)} y2={PAD + SIZE} />

    <!-- The four side names, in the organiser's own words, at the edge
         each one belongs to. -->
    <text class="edge-label" x={PAD - 4} y={py(0)} text-anchor="end" dominant-baseline="middle">
      {xAxis?.low_name}
    </text>
    <text class="edge-label" x={PAD + SIZE + 4} y={py(0)} text-anchor="start" dominant-baseline="middle">
      {xAxis?.high_name}
    </text>
    <text class="edge-label" x={px(0)} y={PAD - 8} text-anchor="middle">{yAxis?.high_name}</text>
    <text class="edge-label" x={px(0)} y={PAD + SIZE + 14} text-anchor="middle">{yAxis?.low_name}</text>

    {#each clusters as cluster, index (`${cluster.x}:${cluster.y}`)}
      <!-- Focusable, and pressing it opens the same label hovering
           does, so a keyboard reaches every dot. ``listitem`` was the
           role here and is one a focusable element may not carry: what
           this behaves like is a button that names who is in the
           cluster. -->
      <g
        class="dot-group"
        class:is-you={cluster.you}
        class:is-active={active === index}
        tabindex="0"
        role="button"
        aria-label={label(cluster)}
        onmouseenter={() => (active = index)}
        onmouseleave={() => (active = null)}
        onfocus={() => (active = index)}
        onblur={() => (active = null)}
        onkeydown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            active = active === index ? null : index;
          }
        }}
      >
        <circle class="dot" cx={px(cluster.x)} cy={py(cluster.y)} r={radius(cluster)} />
        <!-- Drawn last in the group so it sits over the neighbouring
             dots rather than under them. -->
        {#if active === index}
          <text
            class="dot-label"
            x={px(cluster.x)}
            y={py(cluster.y) - radius(cluster) - 2.5}
            text-anchor="middle"
          >
            {label(cluster)}
          </text>
        {/if}
      </g>
    {/each}
  </svg>
</figure>

<style>
.compass-plot {
  /* Centred in whatever card holds it. The square is narrower than the
   * page on every screen that isn't a phone, and a map pinned to the
   * left edge of a wide card reads as a stray illustration rather than
   * as the subject. */
  margin: 0 auto;
  width: 100%;
  max-width: 32rem;
}
.compass-plot.is-compact {
  max-width: 22rem;
}
svg {
  width: 100%;
  height: auto;
  overflow: visible;
}
.quadrants rect {
  fill: var(--brand-red);
  opacity: 0.05;
}
.quadrants rect:nth-child(2n) {
  opacity: 0.02;
}
.frame {
  fill: none;
  stroke: var(--brand-border);
  stroke-width: 0.6;
}
.axis-line {
  stroke: var(--brand-border);
  stroke-width: 0.6;
}
.edge-label {
  font-size: 4.6px;
  font-weight: 600;
  fill: var(--brand-text-muted);
}
.dot-group {
  cursor: default;
  outline: none;
}
.dot {
  fill: var(--brand-text);
  opacity: 0.42;
  transition: opacity 120ms ease;
}
.dot-group.is-active .dot {
  opacity: 0.85;
}
.dot-group.is-you .dot {
  fill: var(--brand-red);
  opacity: 1;
  stroke: var(--brand-surface);
  stroke-width: 1.2;
}
.dot-label {
  font-size: 4.4px;
  fill: var(--brand-text);
  paint-order: stroke;
  stroke: var(--brand-surface);
  stroke-width: 1.6;
  stroke-linejoin: round;
}
/* Keyboard focus has to be visible, and the ring is on the dot rather
 * than the group so it follows the circle's shape. */
.dot-group:focus-visible .dot {
  stroke: var(--brand-red);
  stroke-width: 1.2;
  opacity: 0.95;
}
</style>
