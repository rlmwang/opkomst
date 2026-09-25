/**
 * Where a tour finds the control it lights.
 *
 * A control gets a name where it is rendered, by the ``anchor`` action
 * on the element, and the engine (``docs/design-tour.md`` chapter 5)
 * asks this registry for the element by that name. No selectors: a
 * selector ties a tour to markup that the next restyle changes, a name
 * ties it to what the control means.
 *
 * Two rules keep it simple. A shared component declares a fixed name,
 * so ``list.new`` is the new button on every list page. Where several
 * elements carry one name, the first in document order wins, so every
 * row card registers ``row.details`` and the tour lights the first row.
 */

import { compareDocumentPosition } from "./document-order";

export type AnchorName =
  | "door.form"
  | "door.sent"
  | "home.events"
  | "home.datepolls"
  | "home.chores"
  | "home.forms"
  | "home.quizzes"
  | "home.compasses"
  | "list.new"
  | "list.filter"
  | "list.archived"
  | "row.details"
  | "row.archive"
  | "share.link"
  | "share.qr"
  | "details.edit"
  | "details.recover"
  | "details.signups"
  | "details.feedback"
  | "form.card"
  | "form.title"
  | "form.submit"
  | "form.section.first"
  | "form.section.own"
  | "form.fold"
  | "form.fold.first"
  | "header.menu"
  | "header.subtabs"
  | "admin.approve"
  | "admin.chapter.new"
  | "admin.chapter.row"
  | "admin.agenda";

const registry = new Map<AnchorName, HTMLElement[]>();

// Bumped on every register and unregister. The engine reads it, so a
// step whose control appears after a fetch lands shows the moment it
// does, and an ``until`` step ends the moment its control registers.
let version = $state(0);

export const anchors = {
  get version() {
    return version;
  },
};

export function register(name: AnchorName, el: HTMLElement): void {
  const list = registry.get(name) ?? [];
  if (!list.includes(el)) list.push(el);
  registry.set(name, list);
  version += 1;
}

export function unregister(name: AnchorName, el: HTMLElement): void {
  const list = registry.get(name);
  if (!list) return;
  const i = list.indexOf(el);
  if (i === -1) return;
  list.splice(i, 1);
  if (list.length === 0) registry.delete(name);
  version += 1;
}

/** The first element in document order carrying ``name``, or nothing.
 *  Compared on the document rather than on insertion order, because a
 *  row that mounts late still has to lose to the first row. */
export function resolve(name: AnchorName): HTMLElement | undefined {
  const list = registry.get(name);
  if (!list || list.length === 0) return undefined;
  const live = list.filter((el) => el.isConnected);
  if (live.length === 0) return undefined;
  return live.reduce((first, el) => (compareDocumentPosition(el, first) < 0 ? el : first));
}

/** Svelte action: ``use:anchor={"list.new"}``. Takes an absent name
 *  too, so a component can pass an optional prop straight through. */
export function anchor(node: HTMLElement, name: AnchorName | undefined) {
  let current = name;
  if (current) register(current, node);
  return {
    update(next: AnchorName | undefined) {
      if (next === current) return;
      if (current) unregister(current, node);
      current = next;
      if (current) register(current, node);
    },
    destroy() {
      if (current) unregister(current, node);
    },
  };
}

/** Test seam: forget everything. */
export function resetAnchors(): void {
  registry.clear();
  version += 1;
}
