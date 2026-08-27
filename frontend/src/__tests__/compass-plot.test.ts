/**
 * The map (``CompassPlot.vue``), and the two decisions it carries.
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
import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";

import CompassPlot, { type PlotPoint } from "@/public_shared/CompassPlot.vue";

const AXES = [
  { axis: "x", low_name: "Links", high_name: "Rechts" },
  { axis: "y", low_name: "Open", high_name: "Behoud" },
];

function plot(points: PlotPoint[]) {
  return mount(CompassPlot, { props: { axes: AXES, points, anonymousLabel: "Anoniem" } });
}

function centres(wrapper: ReturnType<typeof plot>) {
  return wrapper.findAll("circle.dot").map((c) => [c.attributes("cx"), c.attributes("cy")]);
}

describe("CompassPlot", () => {
  it("draws the four sides in the organiser's own words", () => {
    const wrapper = plot([{ name: "Sam", x: 0, y: 0 }]);
    const labels = wrapper.findAll("text.edge-label").map((t) => t.text());
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
    const wrapper = plot([
      { name: "Sam", x: 0.5, y: 0.5 },
      { name: "Kim", x: 0.5, y: 0.5 },
      { name: "Bo", x: -0.5, y: 0 },
    ]);
    const dots = wrapper.findAll("circle.dot");
    expect(dots).toHaveLength(2);
    // The stacked one is bigger, and names both of them.
    const groups = wrapper.findAll(".dot-group");
    const stacked = groups.find((g) => g.attributes("aria-label") === "Sam, Kim");
    expect(stacked).toBeTruthy();
    expect(Number(stacked!.find("circle.dot").attributes("r"))).toBeGreaterThan(
      Number(groups.find((g) => g.attributes("aria-label") === "Bo")!.find("circle.dot").attributes("r")),
    );
  });

  it("calls a nameless dot what the caller calls it, and still counts it", () => {
    const wrapper = plot([
      { name: null, x: 0, y: 0 },
      { name: "Sam", x: 0, y: 0 },
    ]);
    expect(wrapper.findAll("circle.dot")).toHaveLength(1);
    expect(wrapper.find(".dot-group").attributes("aria-label")).toBe("Anoniem, Sam");
  });

  it("draws the reader's own dot last, so it lands on top", () => {
    const wrapper = plot([
      { name: "Sam", x: 0, y: 0 },
      { name: "Kim", x: 0.5, y: 0.5, you: true },
      { name: "Bo", x: -0.5, y: 0 },
    ]);
    const groups = wrapper.findAll(".dot-group");
    expect(groups[groups.length - 1].classes()).toContain("is-you");
  });
});
