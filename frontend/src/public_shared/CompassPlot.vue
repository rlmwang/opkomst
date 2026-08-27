<script setup lang="ts">
import { computed, ref } from "vue";

/** The two shapes this reads, declared here rather than imported from
 *  the generated schema: the mini-app bundles do not pull ``api/types``
 *  in, and a plot needs four numbers and a name. */
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
 * budget. It lives in ``public_shared`` and carries no i18n of its own
 * for the same reason ``QuestionField`` does: the organiser's page and
 * the respondent's map are the same picture, and the mini-apps ship
 * without vue-i18n. The two words it needs come in as props.
 */
const props = defineProps<{
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
}>();

// The drawing box. The plot area is 100x100 user units with room
// around it for the four side names; the SVG scales to its container.
const PAD = 22;
const SIZE = 100;
const BOX = SIZE + PAD * 2;

const xAxis = computed(() => props.axes.find((a) => a.axis === "x") ?? null);
const yAxis = computed(() => props.axes.find((a) => a.axis === "y") ?? null);

/** [-1, 1] to the plot box. ``y`` is flipped: the high side of an axis
 *  is drawn at the top, and SVG counts downward. */
function px(value: number): number {
  return PAD + ((value + 1) / 2) * SIZE;
}
function py(value: number): number {
  return PAD + ((1 - value) / 2) * SIZE;
}

interface Cluster {
  x: number;
  y: number;
  names: string[];
  count: number;
  you: boolean;
}

/** Submissions at the same coordinate are one dot. Keyed on the
 *  rounded pair the server already rounded, so two identical answer
 *  sets always land in the same cluster. */
const clusters = computed<Cluster[]>(() => {
  const bySpot = new Map<string, Cluster>();
  for (const point of props.points) {
    const key = `${point.x}:${point.y}`;
    const found = bySpot.get(key);
    const name = point.name ?? props.anonymousLabel;
    if (found) {
      found.names.push(name);
      found.count += 1;
      found.you = found.you || Boolean(point.you);
    } else {
      bySpot.set(key, { x: point.x, y: point.y, names: [name], count: 1, you: Boolean(point.you) });
    }
  }
  // The reader's own dot last, so it draws on top of the room.
  return [...bySpot.values()].sort((a, b) => Number(a.you) - Number(b.you));
});

/** Radius grows with the count and stops growing: a cluster of forty
 *  should read as bigger than one of four and still be a dot. */
function radius(cluster: Cluster): number {
  return 2.2 + Math.min(2.8, Math.sqrt(cluster.count - 1) * 1.1);
}

function label(cluster: Cluster): string {
  return cluster.names.join(", ");
}

// Hover and focus both open the same label, so the map is readable
// with a keyboard and on a phone, where there is no hover at all.
const active = ref<number | null>(null);
</script>

<template>
  <figure class="compass-plot" :class="{ 'is-compact': compact }">
    <svg :viewBox="`0 0 ${BOX} ${BOX}`" role="img" :aria-label="ariaLabel">
      <!-- The four quadrants, tinted so the map reads as four corners
           rather than as a scatter of dots in a box. -->
      <g v-if="!compact" class="quadrants">
        <rect :x="PAD" :y="PAD" :width="SIZE / 2" :height="SIZE / 2" />
        <rect :x="PAD + SIZE / 2" :y="PAD" :width="SIZE / 2" :height="SIZE / 2" />
        <rect :x="PAD" :y="PAD + SIZE / 2" :width="SIZE / 2" :height="SIZE / 2" />
        <rect :x="PAD + SIZE / 2" :y="PAD + SIZE / 2" :width="SIZE / 2" :height="SIZE / 2" />
      </g>

      <rect class="frame" :x="PAD" :y="PAD" :width="SIZE" :height="SIZE" />
      <line class="axis-line" :x1="PAD" :y1="py(0)" :x2="PAD + SIZE" :y2="py(0)" />
      <line class="axis-line" :x1="px(0)" :y1="PAD" :x2="px(0)" :y2="PAD + SIZE" />

      <!-- The four side names, in the organiser's own words, at the
           edge each one belongs to. -->
      <text class="edge-label" :x="PAD - 4" :y="py(0)" text-anchor="end" dominant-baseline="middle">
        {{ xAxis?.low_name }}
      </text>
      <text class="edge-label" :x="PAD + SIZE + 4" :y="py(0)" text-anchor="start" dominant-baseline="middle">
        {{ xAxis?.high_name }}
      </text>
      <text class="edge-label" :x="px(0)" :y="PAD - 8" text-anchor="middle">{{ yAxis?.high_name }}</text>
      <text class="edge-label" :x="px(0)" :y="PAD + SIZE + 14" text-anchor="middle">{{ yAxis?.low_name }}</text>

      <g
        v-for="(cluster, index) in clusters"
        :key="`${cluster.x}:${cluster.y}`"
        class="dot-group"
        :class="{ 'is-you': cluster.you, 'is-active': active === index }"
        tabindex="0"
        role="listitem"
        :aria-label="label(cluster)"
        @mouseenter="active = index"
        @mouseleave="active = null"
        @focus="active = index"
        @blur="active = null"
      >
        <circle
          class="dot"
          :cx="px(cluster.x)"
          :cy="py(cluster.y)"
          :r="radius(cluster)"
        />
        <!-- Drawn last in the group so it sits over the neighbouring
             dots rather than under them. -->
        <text
          v-if="active === index"
          class="dot-label"
          :x="px(cluster.x)"
          :y="py(cluster.y) - radius(cluster) - 2.5"
          text-anchor="middle"
        >
          {{ label(cluster) }}
        </text>
      </g>
    </svg>
  </figure>
</template>

<style scoped>
.compass-plot {
  margin: 0;
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
