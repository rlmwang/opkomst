/**
 * The map (``CompassPlot.svelte``), and the two decisions it carries.
 *
 * **The domain is fixed at [-1, 1].** Not derived from the data, which
 * is what ``../stemwijzer``'s plot does: a map that rescales as people
 * fill it in is a map where your dot moves after you have seen it. So a
 * point at 0.5 sits at the same place whether the busiest dot on the
 * chart is at 0.6 or at 1.0.
 *
 * **Coincident dots cluster.** Answer sets repeat, especially on a
 * short kompas. Jitter would put a dot where nobody is, so identical
 * coordinates become one bigger dot that names everybody in it.
 */
import { render } from "@testing-library/svelte";
import { describe, expect, it } from "vitest";

import CompassPlot from "@/public_shared/CompassPlot.svelte";
import type { PlotPoint } from "@/public_shared/compass-plot";

const AXES = [
  { axis: "x", low_name: "Links", high_name: "Rechts" },
  { axis: "y", low_name: "Open", high_name: "Behoud" },
];

function plot(points: PlotPoint[]) {
  return render(CompassPlot, { props: { axes: AXES, points, anonymousLabel: "Anoniem" } }).container;
}

const all = (root: HTMLElement, selector: string) =>
  [...root.querySelectorAll(selector)] as HTMLElement[];

function centres(root: HTMLElement) {
  return all(root, "circle.dot").map((c) => [c.getAttribute("cx"), c.getAttribute("cy")]);
}

describe("CompassPlot", () => {
  it("draws the four sides in the organiser's own words", () => {
    const root = plot([{ name: "Sam", x: 0, y: 0 }]);
    const labels = all(root, "text.edge-label").map((t) => t.textContent);
    expect(labels).toEqual(["Links", "Rechts", "Behoud", "Open"]);
  });

  it("puts a dot in the same place whatever else is on the chart", () => {
    const alone = centres(plot([{ name: "Sam", x: 0.5, y: -0.5 }]));
    const crowded = centres(
      plot([
        { name: "Sam", x: 0.5, y: -0.5 },
        { name: "Kim", x: 1, y: 1 },
        { name: "Bo", x: -1, y: -1 },
      ]),
    );
    // The first dot did not move when two further-out ones arrived.
    expect(crowded).toContainEqual(alone[0]);
  });

  it("puts the centre in the centre and the ends at the ends", () => {
    const [centre] = centres(plot([{ name: "Sam", x: 0, y: 0 }]));
    const [topRight] = centres(plot([{ name: "Sam", x: 1, y: 1 }]));
    const [bottomLeft] = centres(plot([{ name: "Sam", x: -1, y: -1 }]));
    expect(centre).toEqual(["72", "72"]);
    // High is right and, because SVG counts downward, up.
    expect(topRight).toEqual(["122", "22"]);
    expect(bottomLeft).toEqual(["22", "122"]);
  });

  it("makes one dot of the people who answered the same way", () => {
    const root = plot([
      { name: "Sam", x: 0.5, y: 0.5 },
      { name: "Kim", x: 0.5, y: 0.5 },
      { name: "Bo", x: -0.5, y: 0 },
    ]);
    expect(all(root, "circle.dot")).toHaveLength(2);
    // The stacked one is bigger, and names both of them.
    const groups = all(root, ".dot-group");
    const radius = (g: HTMLElement) =>
      Number((g.querySelector("circle.dot") as SVGCircleElement).getAttribute("r"));
    const stacked = groups.find((g) => g.getAttribute("aria-label") === "Sam, Kim");
    expect(stacked).toBeTruthy();
    expect(radius(stacked!)).toBeGreaterThan(
      radius(groups.find((g) => g.getAttribute("aria-label") === "Bo")!),
    );
  });

  it("calls a nameless dot what the caller calls it, and still counts it", () => {
    const root = plot([
      { name: null, x: 0, y: 0 },
      { name: "Sam", x: 0, y: 0 },
    ]);
    expect(all(root, "circle.dot")).toHaveLength(1);
    expect(all(root, ".dot-group")[0].getAttribute("aria-label")).toBe("Anoniem, Sam");
  });

  it("draws the reader's own dot last, so it lands on top", () => {
    const root = plot([
      { name: "Sam", x: 0, y: 0 },
      { name: "Kim", x: 0.5, y: 0.5, you: true },
      { name: "Bo", x: -0.5, y: 0 },
    ]);
    const groups = all(root, ".dot-group");
    expect([...groups[groups.length - 1].classList]).toContain("is-you");
  });
});
