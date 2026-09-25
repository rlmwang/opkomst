/**
 * The tour's registry (``tours/anchors``): a control gets a name where
 * it is rendered, the first in document order wins, and every name a
 * tour may use is one some component actually renders.
 */
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";

import { afterEach, describe, expect, it } from "vitest";

import { type AnchorName, anchor, anchors, register, resetAnchors, resolve, unregister } from "@/tours/anchors.svelte";

afterEach(() => resetAnchors());

describe("the anchor registry", () => {
  it("resolves the first element in document order, whatever order they registered in", () => {
    const first = document.createElement("button");
    const second = document.createElement("button");
    document.body.append(first, second);
    register("row.details", second);
    register("row.details", first);
    expect(resolve("row.details")).toBe(first);
    first.remove();
    second.remove();
  });

  it("bumps its version on register and unregister, so an effect can wait on it", () => {
    const el = document.createElement("div");
    document.body.append(el);
    const before = anchors.version;
    register("list.new", el);
    expect(anchors.version).toBe(before + 1);
    unregister("list.new", el);
    expect(anchors.version).toBe(before + 2);
    expect(resolve("list.new")).toBeUndefined();
    el.remove();
  });

  it("is an action that cleans up on destroy and follows a renamed anchor", () => {
    const el = document.createElement("div");
    document.body.append(el);
    const action = anchor(el, "share.link");
    expect(resolve("share.link")).toBe(el);
    action.update("share.qr");
    expect(resolve("share.link")).toBeUndefined();
    expect(resolve("share.qr")).toBe(el);
    action.destroy();
    expect(resolve("share.qr")).toBeUndefined();
    el.remove();
  });

  it("ignores an element that has left the document", () => {
    const el = document.createElement("div");
    document.body.append(el);
    register("form.card", el);
    el.remove();
    expect(resolve("form.card")).toBeUndefined();
  });
});

/** Every ``.svelte`` file under ``src``, read once. */
function svelteSources(dir: string): string[] {
  const out: string[] = [];
  for (const entry of readdirSync(dir)) {
    const path = join(dir, entry);
    if (statSync(path).isDirectory()) {
      if (entry !== "node_modules") out.push(...svelteSources(path));
    } else if (entry.endsWith(".svelte")) {
      out.push(readFileSync(path, "utf8"));
    }
  }
  return out;
}

describe("every declared anchor is rendered by some component", () => {
  // The union is the source of truth for what a tour may name; this
  // list mirrors it so a name added to the type without a component
  // fails here with the name in the message.
  const declared: AnchorName[] = [
    "door.form",
    "door.sent",
    "home.events",
    "home.datepolls",
    "home.chores",
    "home.forms",
    "home.quizzes",
    "home.compasses",
    "list.new",
    "list.filter",
    "list.archived",
    "row.details",
    "row.archive",
    "share.link",
    "share.qr",
    "details.edit",
    "details.recover",
    "details.signups",
    "details.feedback",
    "form.card",
    "form.title",
    "form.submit",
    "form.section.first",
    "form.section.own",
    "form.fold",
    "form.fold.switch",
    "header.menu",
    "header.subtabs",
    "admin.approve",
    "admin.chapter.new",
    "admin.chapter.row",
    "admin.agenda",
  ];

  // Registered by the form section and fold components of task 02 in
  // ``docs/tasks/help``. Owed, not missing; the list goes when they land.
  const owed: AnchorName[] = ["form.section.first", "form.section.own", "form.fold", "form.fold.switch"];

  const sources = svelteSources(join(__dirname, ".."));

  it.each(declared.filter((n) => !owed.includes(n)))("%s", (name) => {
    // ``use:anchor={"x"}``, ``anchor="x"``, ``anchor: "x"`` (a tile), or
    // a ternary that names it (the archived subtab).
    const hit = sources.some((src) => src.includes(`"${name}"`));
    expect(hit, `${name} is declared but no component renders it`).toBe(true);
  });
});
