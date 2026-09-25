/**
 * The six tours as data (``tours/tours``), their words, and which page
 * offers which (``tours/index``).
 */
import { describe, expect, it } from "vitest";

import en from "@/locales/en.json";
import nl from "@/locales/nl.json";
import { PRODUCTS, manualChapterFor, tourFor } from "@/tours";
import { TOURS } from "@/tours/tours";
import type { TourId } from "@/tours/types";

type Node = string | { [key: string]: Node };

function lookup(root: Node, key: string): string | undefined {
  let node: Node | undefined = root;
  for (const part of key.split(".")) {
    if (typeof node !== "object") return undefined;
    node = node[part];
  }
  return typeof node === "string" ? node : undefined;
}

function sentences(text: string): number {
  return text.split(/[.?!]\s+|[.?!]$/).filter((s) => s.trim().length > 0).length;
}

const ids = Object.keys(TOURS) as TourId[];

describe("the tours", () => {
  it("are six, with at most five steps each", () => {
    expect(ids).toHaveLength(6);
    for (const id of ids) expect(TOURS[id].steps.length, id).toBeLessThanOrEqual(5);
  });

  it("run on the page they were started from, or name their pages", () => {
    for (const id of ids) {
      const tour = TOURS[id];
      for (const step of tour.steps) {
        if (tour.perPage) expect(step.page, `${id} is per page`).toBeUndefined();
        else expect(step.page, `${id} crosses pages`).toBeDefined();
      }
    }
  });

  it.each(ids)("%s has a title and a body for every step in both languages", (id) => {
    const tour = TOURS[id];
    tour.steps.forEach((_, i) => {
      for (const [lang, root] of [
        ["nl", nl],
        ["en", en],
      ] as const) {
        const n = i + 1;
        const title = lookup(root as Node, `tour.${id}.${n}.title`);
        const body = lookup(root as Node, `tour.${id}.${n}.body`);
        expect(title, `${lang} tour.${id}.${n}.title`).toBeDefined();
        expect(body, `${lang} tour.${id}.${n}.body`).toBeDefined();
      }
    });
  });

  it("says at most two sentences per step, in every variant, and titles as short questions", () => {
    const walk = (node: Node, path: string) => {
      if (typeof node === "string") {
        if (path.endsWith(".body")) expect(sentences(node), `${path}: ${node}`).toBeLessThanOrEqual(2);
        if (path.endsWith(".title")) {
          expect(node.endsWith("?"), `${path}: ${node}`).toBe(true);
          expect(node.split(/\s+/).length, `${path}: ${node}`).toBeLessThanOrEqual(6);
        }
        return;
      }
      for (const [k, v] of Object.entries(node)) walk(v, `${path}.${k}`);
    };
    for (const root of [nl, en]) {
      const tour = (root as { tour: Node }).tour as { [key: string]: Node };
      for (const id of ids) walk(tour[id], `tour.${id}`);
    }
  });

  it("carries an organisation variant only where the door differs", () => {
    expect(lookup(nl as Node, "tour.inloggen.4.organisation.body")).toBeDefined();
    expect(lookup(en as Node, "tour.inloggen.4.organisation.body")).toBeDefined();
  });
});

describe("which page offers which tour", () => {
  it.each(PRODUCTS)("%s: list, archive, form and details pages", (product) => {
    expect(tourFor(`/${product}`)).toEqual({ id: "lijst", product });
    expect(tourFor(`/${product}/archived`)).toEqual({ id: "lijst", product });
    expect(tourFor(`/${product}/new`)).toEqual({ id: "formulier", product });
    expect(tourFor(`/${product}/abc/edit`)).toEqual({ id: "formulier", product });
    expect(tourFor(`/${product}/abc/details`)).toEqual({ id: "details", product });
  });

  it("offers the admin tour on the three admin pages and nothing elsewhere", () => {
    for (const p of ["/users", "/chapters", "/settings"]) expect(tourFor(p)).toEqual({ id: "beheer", product: null });
    expect(tourFor("/")).toBeNull();
    expect(tourFor("/auth/redeem")).toBeNull();
    expect(tourFor("/e/abc/feedback")).toBeNull();
  });
});

describe("which chapter the menu opens", () => {
  it("is the product's chapter, the sign-ups chapter on an event's details, and the archive on any archive", () => {
    expect(manualChapterFor("/")).toBeNull();
    expect(manualChapterFor("/event")).toBe(2);
    expect(manualChapterFor("/event/new")).toBe(2);
    expect(manualChapterFor("/event/abc/details")).toBe(3);
    expect(manualChapterFor("/event/archived")).toBe(10);
    expect(manualChapterFor("/datepoll/abc/details")).toBe(5);
    expect(manualChapterFor("/chore")).toBe(6);
    expect(manualChapterFor("/form/new")).toBe(7);
    expect(manualChapterFor("/quiz/archived")).toBe(10);
    expect(manualChapterFor("/compass")).toBe(9);
    expect(manualChapterFor("/users")).toBe(13);
    expect(manualChapterFor("/chapters")).toBe(12);
    expect(manualChapterFor("/settings")).toBe(12);
    expect(manualChapterFor("/auth/redeem")).toBeNull();
  });
});
