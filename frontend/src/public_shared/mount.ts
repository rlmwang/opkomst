/**
 * Mounting a public mini-app.
 *
 * Every public shell paints a boot spinner inside ``#app`` so a slow
 * connection shows something before the bundle lands. Vue's ``mount``
 * replaced the container's children with the app; Svelte's appends to
 * it, so the spinner has to be cleared here or it stays on top of the
 * page and swallows every click (found by the forms e2e, which timed
 * out clicking a rating dot the spinner was covering).
 */
import { mount, type Component } from "svelte";

export function mountPublic(component: Component<Record<string, never>>): void {
  const target = document.getElementById("app")!;
  target.replaceChildren();
  mount(component, { target });
}
