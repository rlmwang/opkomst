<script lang="ts">
import AppInput from "@/components/AppInput.svelte";
import { t } from "@/i18n.svelte";
import type { CompassAxisIn } from "@/api/types";

/**
 * The two axes a kompas places people on, and the four sides those
 * axes have (``docs/design-kompas.md`` 4.1).
 *
 * Every one of the four sides is named, because the result screen
 * builds a sentence out of them and an unnamed side is a sentence with
 * a hole in it. A name is also *all* a side gets: a description per
 * side was six more boxes for four words the axis's own description
 * already covers, and half-filled they leave a result screen that
 * explains two sides out of four.
 *
 * What the card does not carry either is a word above each box: a field
 * label and a placeholder said the same thing twice. The placeholder
 * carries what to type and the example to type it like, and the one
 * thing a placeholder cannot say, which is where a side lands on the
 * map, is an arrow beside it.
 *
 * The two examples are the political compass's own axes
 * (``../stemwijzer/KOMPAS.md``): an economic one and a
 * social-cultural one, so the second card never repeats the first
 * card's words.
 */
let { value = $bindable() }: { value: CompassAxisIn[] } = $props();

const AXIS = { x: "X", y: "Y" } as const;
/** ``low`` is drawn left on x and bottom on y, so the arrow points the
 *  way the dot moves. */
const ARROW = { x: { low: "←", high: "→" }, y: { low: "↓", high: "↑" } } as const;

/** The rows sit in the order the map draws them: left before right,
 *  and top before bottom. A down arrow above an up arrow is a card
 *  standing on its head. */
const SIDES = { x: ["low", "high"], y: ["high", "low"] } as const;

function copy(axis: "x" | "y", key: string): string {
  return t(`compass.edit.${key}${AXIS[axis]}`);
}

function sideLabel(axis: "x" | "y", side: "low" | "high"): string {
  return copy(axis, side === "low" ? "sideLow" : "sideHigh");
}

/** A kompas always has both. A payload that arrived without them (a
 *  draft saved before the axes were filled in) gets the empty pair, so
 *  the page renders the same two cards either way. */
function axisAt(axis: "x" | "y"): CompassAxisIn {
  return (
    value.find((a) => a.axis === axis) ?? {
      axis,
      name: "",
      description: null,
      low_name: "",
      high_name: "",
    }
  );
}

type TextKey = "name" | "description" | "low_name" | "high_name";

function patch(axis: "x" | "y", key: TextKey, raw: string | null | undefined): void {
  // The three names are not nullable on the wire, and an empty box is
  // the state an organiser is in halfway through filling this out. The
  // empty string keeps that expressible, and the save refuses it by
  // name rather than the field silently dropping out of the payload.
  const nullable = key === "description";
  const cleaned = nullable ? ((raw ?? "").trim() === "" ? null : (raw ?? "")) : (raw ?? "");
  const next = { ...axisAt(axis), [key]: cleaned } as CompassAxisIn;
  value = [axis === "x" ? next : axisAt("x"), axis === "y" ? next : axisAt("y")];
}
</script>

<div class="axes-editor">
  {#each ["x", "y"] as const as axis (axis)}
    <div class="axis-card">
      <h3 class="axis-heading">{t(`compass.edit.axis${AXIS[axis]}`)}</h3>

      <AppInput
        value={axisAt(axis).name}
        placeholder={copy(axis, "axisNamePlaceholder")}
        fluid
        oninput={(e) => patch(axis, "name", (e.currentTarget as HTMLInputElement).value)}
      />
      <AppInput
        value={axisAt(axis).description ?? ""}
        placeholder={copy(axis, "axisDescriptionPlaceholder")}
        fluid
        oninput={(e) => patch(axis, "description", (e.currentTarget as HTMLInputElement).value)}
      />

      <!-- The two sides, in the order the plot draws them. The arrow is
           the one thing the boxes cannot say themselves; it carries the
           words for a screen reader. -->
      {#each SIDES[axis] as side (side)}
        <div class="side-row">
          <span class="side-arrow" title={sideLabel(axis, side)} aria-hidden="true"
            >{ARROW[axis][side]}</span
          >
          <AppInput
            value={side === "low" ? axisAt(axis).low_name : axisAt(axis).high_name}
            placeholder={copy(axis, side === "low" ? "lowNamePlaceholder" : "highNamePlaceholder")}
            fluid
            oninput={(e) =>
              patch(
                axis,
                side === "low" ? "low_name" : "high_name",
                (e.currentTarget as HTMLInputElement).value,
              )}
          />
        </div>
      {/each}
    </div>
  {/each}
</div>

<style>
.axes-editor {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(20rem, 1fr));
  gap: 0.75rem;
}
.axis-card {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  padding: 0.875rem 1rem;
  border: 1px solid var(--brand-border);
  border-radius: 8px;
  background: var(--brand-surface);
}
.axis-heading {
  margin: 0;
  font-size: 1rem;
}
.side-row {
  display: flex;
  gap: 0.5rem;
  align-items: center;
  min-width: 0;
}
/* Fixed width so the two rows' boxes line up under each other, and the
 * arrow reads as a gutter rather than as part of the first field. Big
 * enough to read as a direction: at body size it looked like
 * punctuation. */
.side-arrow {
  flex: 0 0 1.25rem;
  text-align: center;
  font-size: 1.375rem;
  line-height: 1;
  color: var(--brand-text-muted);
  cursor: default;
}
.side-row :global(.app-input) {
  min-width: 0;
}
</style>
