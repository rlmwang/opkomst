import { anchors, registered, resolve } from "@/tours/anchors.svelte";
import { next, skip, stop, tour } from "@/stores/tour.svelte";
import { compile } from "@/router/router.svelte";
import type { ResolvedStep } from "./types";

/**
 * Following the route (``docs/design-tour.md`` chapter 8).
 *
 * One effect over the current path, the registry's change count, the
 * number of requests in flight and the step index, with five outcomes:
 *
 * 1. The path matches the step's page and its control is registered:
 *    show it.
 * 2. The path matches and a request is in flight: the page is still
 *    filling. Wait.
 * 3. The path matches, nothing is in flight, and the control is not
 *    registered: drop the step.
 * 4. The path does not match, but the step before was a click, or this
 *    step is an ``until``, and the path still belongs to one of the two
 *    pages that navigation runs between: it has not landed. Wait.
 * 5. Otherwise the person went somewhere else. Stop.
 *
 * The requests in flight are the query client's own count. Counting
 * frames guessed at how long a fetch takes, and guessed wrong for a
 * details page reached by a save rather than a hover.
 */

export interface EngineDeps {
  path: () => string;
  fetching: () => number;
  /** Runs ``fn`` once the page has had a frame to draw. Two animation
   *  frames in the app; a test hands over something it can run itself. */
  afterPaint?: (fn: () => void) => void;
}

function twoFrames(fn: () => void): void {
  requestAnimationFrame(() => requestAnimationFrame(fn));
}

export interface Shown {
  step: ResolvedStep;
  el: HTMLElement;
}

function matches(pattern: string | undefined, path: string): boolean {
  if (pattern === undefined) return true;
  return compile(pattern).re.test(path);
}

export function createEngine(deps: EngineDeps) {
  const afterPaint = deps.afterPaint ?? twoFrames;
  let shown = $state<Shown | null>(null);
  // The path the page has had a frame to draw for. The route changes
  // before the new page's controls can register, so a step is dropped
  // for an absent control only once its page has painted; until then
  // the page is still arriving, whatever the fetch count says.
  let painted = $state<string | null>(null);
  $effect(() => {
    const path = deps.path();
    painted = null;
    afterPaint(() => {
      if (deps.path() === path) painted = path;
    });
  });
  // Every element carrying an until step's name when the step became
  // current. The step ends on a control that appeared since, not on
  // one that was already there: the list page has a share link on
  // every row, and the welcome tour's form step waits for the details
  // page's, not for those. All of them, not the first: as the list
  // page leaves, its rows unregister one by one, and for a moment the
  // second row is the first.
  let baseline: { index: number; els: Set<HTMLElement> } | null = null;
  // The step that has been on screen. Once a step has shown, the
  // navigation the click before it asked for has landed, so leaving
  // its page afterwards is the person leaving, not the page arriving.
  let landed: number | null = null;

  $effect(() => {
    const step = tour.step;
    if (!step) {
      shown = null;
      baseline = null;
      landed = null;
      return;
    }
    // Read once, so the effect re-runs on any of them.
    void anchors.version;
    const path = deps.path();
    const fetching = deps.fetching();

    // An until step ends the moment its control appears, wherever the
    // person is: that is how the form step learns the save landed.
    if (step.advance.kind === "until") {
      if (baseline?.index !== tour.index) {
        baseline = { index: tour.index, els: new Set(registered(step.advance.name)) };
      }
      const target = resolve(step.advance.name);
      if (target && !baseline.els.has(target)) {
        shown = null;
        next();
        return;
      }
    }

    if (matches(step.page, path)) {
      const el = resolve(step.anchor);
      if (el) {
        shown = shown?.el === el && shown.step === step ? shown : { step, el };
        landed = tour.index;
        return;
      }
      shown = null;
      if (fetching > 0 || painted !== path) return;
      skip();
      return;
    }

    // Off the step's page. An until step is waiting for the navigation
    // to the next step's page; after a click step, the navigation from
    // the previous step's page has not landed. Anywhere else is the
    // person leaving.
    shown = null;
    const previous = tour.previous;
    const afterClick =
      landed !== tour.index &&
      previous !== null &&
      previous.advance.kind === "click" &&
      matches(previous.page, path);
    const beforeNext = step.advance.kind === "until" && matches(nextPage(), path);
    if (!afterClick && !beforeNext) stop();
  });

  /** The page after an until step, for the navigation it waits on. */
  function nextPage(): string | undefined {
    return tour.steps[tour.index + 1]?.page;
  }

  return {
    get shown() {
      return shown;
    },
  };
}
