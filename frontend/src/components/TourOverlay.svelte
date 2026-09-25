<script lang="ts">
import { onMount, tick } from "svelte";

import { placePanel } from "@/composables/overlay-panel";
import { t, te } from "@/i18n.svelte";
import { isPersonalApp } from "@/lib/branding";
import { queryClient } from "@/lib/query-client";
import { route } from "@/router/navigation.svelte";
import { next, restart, stop, tour } from "@/stores/tour.svelte";
import { createEngine } from "@/tours/engine.svelte";
import { calloutSheet, holeGeometry, maskPath } from "@/tours/geometry";

/**
 * The guide (``docs/design-tour.md`` chapters 6 and 7): a mask over the
 * whole page with one hole in it, and a callout beside the hole.
 *
 * The mask is one SVG path, the viewport minus a rounded rectangle,
 * filled even-odd. Its fill takes pointer events, so a click on the
 * dark part lands here and goes no further, and a click in the hole
 * reaches the real control. Four rectangles could not do this: a
 * rounded hole has corners they would leave open.
 *
 * The callout is a dialog by role and not a ``<dialog>`` opened
 * modally: a modal makes the page inert, and a click step needs the
 * one control in the hole to stay live.
 *
 * Mounted once in the app shell, loaded only when a tour is running.
 */

const PAD = 8;
const GUTTER = 10;

// The query client's own count of requests in flight, as state the
// engine's effect can read.
let fetching = $state(queryClient.isFetching());
onMount(() =>
  queryClient.getQueryCache().subscribe(() => {
    fetching = queryClient.isFetching();
  }),
);

const engine = createEngine({ path: () => route.path, fetching: () => fetching });

let callout = $state<HTMLElement | undefined>();
let hole = $state<{ x: number; y: number; w: number; h: number; r: number } | null>(null);
let viewport = $state({ w: window.innerWidth, h: window.innerHeight });
let calloutStyle = $state<Record<string, string>>({});
let flipped = $state(false);
let arrowLeft = $state(`${GUTTER}px`);

const shown = $derived(engine.shown);
const step = $derived(shown?.step ?? null);
const isNextStep = $derived(step?.advance.kind === "next");
const sheet = $derived(hole !== null && calloutSheet(viewport, hole));
const total = $derived(tour.steps.length);
const index = $derived(tour.index);

function measure(): void {
  const el = shown?.el;
  if (!el) return;
  viewport = { w: window.innerWidth, h: window.innerHeight };
  hole = holeGeometry(el, PAD);
  if (callout && !sheet) {
    const box = {
      left: hole.x,
      top: hole.y,
      right: hole.x + hole.w,
      bottom: hole.y + hole.h,
      width: hole.w,
      height: hole.h,
    };
    const anchor = { getBoundingClientRect: () => box as DOMRect } as HTMLElement;
    const placed = placePanel(anchor, callout, { matchAnchorWidth: false, gutter: GUTTER, align: "center" });
    calloutStyle = placed.style;
    flipped = placed.flipped;
    const panel = callout.getBoundingClientRect();
    const centre = hole.x + hole.w / 2 - parseFloat(placed.style.insetInlineStart);
    arrowLeft = `${Math.max(GUTTER + 2, Math.min(centre, panel.width - GUTTER - 2))}px`;
  }
}

// On every step: scroll the control into view, measure on the next
// frame, and again on resize, on any scroll, and when the control's own
// size changes.
$effect(() => {
  const el = shown?.el;
  if (!el) {
    hole = null;
    return;
  }
  const phone = window.matchMedia("(max-width: 480px)").matches;
  el.scrollIntoView({ block: phone ? "start" : "center", inline: "nearest" });
  const frame = requestAnimationFrame(() => {
    measure();
    void tick().then(() => {
      measure();
      callout?.focus({ preventScroll: true });
    });
  });
  const observer = new ResizeObserver(() => measure());
  observer.observe(el);
  window.addEventListener("resize", measure);
  window.addEventListener("scroll", measure, true);
  return () => {
    cancelAnimationFrame(frame);
    observer.disconnect();
    window.removeEventListener("resize", measure);
    window.removeEventListener("scroll", measure, true);
  };
});

// A click step advances from the control itself: a one-shot listener
// in the capture phase that does not stop the event, so the real
// handler runs and the navigation it causes is what the engine waits
// for.
$effect(() => {
  const el = shown?.el;
  const s = shown?.step;
  if (!el || !s || s.advance.kind !== "click") return;
  const onClick = () => next();
  el.addEventListener("click", onClick, { capture: true, once: true });
  return () => el.removeEventListener("click", onClick, { capture: true });
});

// Tab from the highlighted control comes back to the callout, so the
// one thing outside it that may be pressed is reachable and nothing
// else is. Only from the control itself: inside a lit form, Tab moves
// between its fields as it always does.
$effect(() => {
  const el = shown?.el;
  if (!el) return;
  const onKey = (event: KeyboardEvent) => {
    if (event.key !== "Tab" || event.target !== el) return;
    event.preventDefault();
    buttons()[0]?.focus();
  };
  el.addEventListener("keydown", onKey);
  return () => el.removeEventListener("keydown", onKey);
});

function buttons(): HTMLElement[] {
  return Array.from(callout?.querySelectorAll<HTMLElement>("button") ?? []);
}

function onKeydown(event: KeyboardEvent): void {
  if (event.key === "Escape") {
    event.preventDefault();
    stop();
    return;
  }
  if (event.key === "Enter" || event.key === "ArrowRight") {
    if ((event.target as HTMLElement).tagName === "BUTTON" && event.key === "Enter") return;
    event.preventDefault();
    next();
    return;
  }
  if (event.key !== "Tab") return;
  const list = buttons();
  if (list.length === 0) return;
  const first = list[0];
  const last = list[list.length - 1];
  const active = document.activeElement;
  const outside = !isNextStep ? shown?.el : undefined;
  if (event.shiftKey && (active === first || active === callout)) {
    event.preventDefault();
    (outside ?? last)?.focus();
  } else if (!event.shiftKey && active === last) {
    event.preventDefault();
    (outside ?? first)?.focus();
  }
}

/** The words for a step, by tour, product and declared position, the
 *  product's own key first. The sign-in tour's last step has an
 *  organisation variant, chosen by the same switch the door uses. */
function words(kind: "title" | "body"): string {
  if (!step || !tour.id) return "";
  const base = `tour.${tour.id}`;
  const keys = [
    ...(tour.product ? [`${base}.${tour.product}.${step.n}.${kind}`] : []),
    ...(isPersonalApp() ? [] : [`${base}.${step.n}.organisation.${kind}`]),
    `${base}.${step.n}.${kind}`,
  ];
  return t(keys.find((k) => te(k)) ?? keys[keys.length - 1]);
}

function styleOf(style: Record<string, string>): string {
  return Object.entries(style)
    .map(([k, v]) => `${k.replace(/[A-Z]/g, (m) => `-${m.toLowerCase()}`)}: ${v}`)
    .join("; ");
}
</script>

{#if shown && hole}
  <svg
    class="tour-mask"
    width={viewport.w}
    height={viewport.h}
    viewBox="0 0 {viewport.w} {viewport.h}"
    aria-hidden="true"
    onclick={(e) => e.stopPropagation()}
  >
    <path d={maskPath(viewport, hole)} fill-rule="evenodd" class="tour-mask-fill" />
    <rect
      x={hole.x - 2}
      y={hole.y - 2}
      width={hole.w + 4}
      height={hole.h + 4}
      rx={hole.r + 2}
      ry={hole.r + 2}
      class="tour-ring"
    />
  </svg>
  <div
    bind:this={callout}
    class="tour-callout"
    class:tour-sheet={sheet}
    class:tour-flipped={flipped}
    style={sheet ? "" : `${styleOf(calloutStyle)}; --tour-arrow-left: ${arrowLeft}`}
    role="dialog"
    aria-labelledby="tour-title"
    tabindex="-1"
    onkeydown={onKeydown}
  >
    <div aria-live="polite">
      <p class="tour-counter muted">{t("tour.counter", { n: index + 1, total })}</p>
      <h2 id="tour-title" class="tour-title">{words("title")}</h2>
      <p class="tour-body">{words("body")}</p>
    </div>
    <!-- Stoppen on the left; Volgende on the right on every step, so
         the way on is always the same button in the same place. A
         click step advances by itself when the control is pressed, and
         Volgende goes on regardless. Only the last step offers a way
         back, to the start, beside Klaar. -->
    <div class="tour-buttons">
      <button type="button" class="tour-btn tour-btn-text" onclick={() => stop()}>{t("tour.stop")}</button>
      <span class="tour-spacer"></span>
      {#if index + 1 >= total}
        <button type="button" class="tour-btn tour-btn-secondary" onclick={() => restart()}>{t("tour.again")}</button>
        <button type="button" class="tour-btn tour-btn-primary" onclick={() => next()}>{t("tour.done")}</button>
      {:else}
        <button type="button" class="tour-btn tour-btn-primary" onclick={() => next()}>{t("tour.next")}</button>
      {/if}
    </div>
  </div>
{/if}

<style>
/* Above the page and below every floating thing the app already has:
 * toasts at 1000, the popover at 1100, the tooltip at 1200. The toast
 * that says an event needs a name is what the form step depends on. */
.tour-mask {
  position: fixed;
  inset: 0;
  z-index: 990;
  pointer-events: none;
}
.tour-mask-fill {
  fill: rgba(0, 0, 0, 0.55);
  pointer-events: fill;
}
/* The ring theme.css gives a link or button on keyboard focus, so the
 * hole says "look here" in a language the app already speaks. */
.tour-ring {
  fill: none;
  stroke: var(--brand-red);
  stroke-width: 2;
  pointer-events: none;
}
/* The popover's geometry: surface, border, radius, shadow, an arrow. */
.tour-callout {
  position: fixed;
  z-index: 1100;
  max-width: 20rem;
  padding: 1rem;
  background: var(--brand-surface);
  color: var(--brand-text);
  border: 1px solid var(--brand-border);
  border-radius: 6px;
  box-shadow:
    0 4px 6px -1px rgba(0, 0, 0, 0.1),
    0 2px 4px -2px rgba(0, 0, 0, 0.1);
  outline: none;
}
.tour-callout::before,
.tour-callout::after {
  content: " ";
  position: absolute;
  bottom: 100%;
  left: var(--tour-arrow-left);
  height: 0;
  width: 0;
  pointer-events: none;
  border-style: solid;
  border-color: transparent;
}
.tour-callout::after {
  border-width: 8px;
  margin-left: -8px;
  border-bottom-color: var(--brand-surface);
}
.tour-callout::before {
  border-width: 10px;
  margin-left: -10px;
  border-bottom-color: var(--brand-border);
}
.tour-flipped::before,
.tour-flipped::after {
  bottom: auto;
  top: 100%;
}
.tour-flipped::after {
  border-bottom-color: transparent;
  border-top-color: var(--brand-surface);
}
.tour-flipped::before {
  border-bottom-color: transparent;
  border-top-color: var(--brand-border);
}
/* On a phone, and beside a hole taller than most of the screen, a
 * sheet across the bottom instead of a popover with nowhere to be. */
.tour-sheet {
  inset: auto 0 0 0;
  max-width: none;
  border-radius: 6px 6px 0 0;
  border-bottom: none;
}
.tour-sheet::before,
.tour-sheet::after {
  display: none;
}
.tour-counter {
  margin: 0 0 0.25rem;
  font-size: 0.8125rem;
}
.tour-title {
  margin: 0 0 0.5rem;
  font-size: 1rem;
  font-weight: 600;
}
.tour-body {
  margin: 0 0 1rem;
  font-size: 0.875rem;
}
.tour-buttons {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}
.tour-spacer {
  margin-left: auto;
}
.tour-btn {
  font-family: inherit;
  font-size: 0.875rem;
  padding: 0.375rem 0.625rem;
  border: 1px solid transparent;
  border-radius: 6px;
  cursor: pointer;
}
.tour-btn-primary {
  background: var(--brand-red);
  color: var(--brand-surface);
}
.tour-btn-secondary {
  background: var(--brand-surface);
  color: var(--brand-text);
  border-color: var(--brand-border);
}
.tour-btn-text {
  background: transparent;
  color: var(--brand-text-muted);
}
</style>
