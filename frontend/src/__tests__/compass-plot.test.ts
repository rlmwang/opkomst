/**
 * The map (``CompassPlot.svelte``), and the two decisions it carries.
 *
 * **The domain is fixed at [-1, 1].** Not derived from the data, which
 * is what ``../stemwijzer``'s plot does: a map that rescales as people
 * fill it in is a map where your dot moves after you have seen it. So a
 * point at 0.5 sits at the same place whether the busiest dot on the
 * chart is at 0.6 or at 1.0.
 *
 * **Coincident dots are one dot.** Answer sets repeat, especially on a
 * short kompas. Jitter would put a dot where nobody is, so identical
 * coordinates arrive as one spot: a count, and the first few names in
 * it. The grouping is the database's (``services/compass``); what is
 * tested here is the drawing of it.
 */
import { render } from "@testing-library/svelte";
import { describe, expect, it } from "vitest";

import CompassPlot from "@/public_shared/CompassPlot.svelte";
import type { PlotSpot } from "@/public_shared/compass-plot";

const AXES = [
  { axis: "x", low_name: "Links", high_name: "Rechts" },
  { axis: "y", low_name: "Open", high_name: "Behoud" },
];

function plot(points: PlotSpot[]) {
  return render(CompassPlot, { props: { axes: AXES, points, anonymousLabel: "Anoniem" } }).container;
}

const all = (root: HTMLElement, selector: string) =>
  [...root.querySelectorAll(selector)] as HTMLElement[];

function centres(root: HTMLElement) {
  return all(root, "circle.dot").map((c) => [c.getAttribute("cx"), c.getAttribute("cy")]);
}

describe("CompassPlot", () => {
  it("draws the four sides in the organiser's own words", () => {
    const root = plot([{ x: 0, y: 0, count: 1, names: ["Sam"] }]);
    const labels = all(root, "text.edge-label").map((t) => t.textContent);
    expect(labels).toEqual(["Links", "Rechts", "Behoud", "Open"]);
  });

  it("puts a dot in the same place whatever else is on the chart", () => {
    const alone = centres(plot([{ x: 0.5, y: -0.5, count: 1, names: ["Sam"] }]));
    const crowded = centres(
      plot([
        { x: 0.5, y: -0.5, count: 1, names: ["Sam"] },
        { x: 1, y: 1, count: 1, names: ["Kim"] },
        { x: -1, y: -1, count: 1, names: ["Bo"] },
      ]),
    );
    // The first dot did not move when two further-out ones arrived.
    expect(crowded).toContainEqual(alone[0]);
  });

  it("puts the centre in the centre and the ends at the ends", () => {
    const [centre] = centres(plot([{ x: 0, y: 0, count: 1, names: ["Sam"] }]));
    const [topRight] = centres(plot([{ x: 1, y: 1, count: 1, names: ["Sam"] }]));
    const [bottomLeft] = centres(plot([{ x: -1, y: -1, count: 1, names: ["Sam"] }]));
    expect(centre).toEqual(["72", "72"]);
    // High is right and, because SVG counts downward, up.
    expect(topRight).toEqual(["122", "22"]);
    expect(bottomLeft).toEqual(["22", "122"]);
  });

  it("draws a crowded dot bigger, and names who is in it", () => {
    const root = plot([
      { x: 0.5, y: 0.5, count: 2, names: ["Sam", "Kim"] },
      { x: -0.5, y: 0, count: 1, names: ["Bo"] },
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

  it("calls a nameless dot what the caller calls it", () => {
    const root = plot([{ x: 0, y: 0, count: 2, names: [null, "Sam"] }]);
    expect(all(root, "circle.dot")).toHaveLength(1);
    expect(all(root, ".dot-group")[0].getAttribute("aria-label")).toBe("Anoniem, Sam");
  });

  it("ends a crowded dot's label in an ellipsis", () => {
    // The server sends the first five names of a dot holding nine
    // hundred people. The label says so rather than pretending five is
    // everybody.
    const root = plot([
      { x: 0, y: 0, count: 900, names: ["Sam", "Kim", "Bo", "Jo", "Robin"] },
    ]);
    expect(all(root, ".dot-group")[0].getAttribute("aria-label")).toBe("Sam, Kim, Bo, Jo, Robin, …");
  });

  it("draws the reader's own dot last, so it lands on top", () => {
    const root = plot([
      { x: 0, y: 0, count: 1, names: ["Sam"] },
      { x: 0.5, y: 0.5, count: 1, names: ["Kim"], you: true },
      { x: -0.5, y: 0, count: 1, names: ["Bo"] },
    ]);
    const groups = all(root, ".dot-group");
    expect([...groups[groups.length - 1].classList]).toContain("is-you");
  });
});
