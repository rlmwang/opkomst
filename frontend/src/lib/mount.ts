import { mount, type Component } from "svelte";

/**
 * Put an app on the page.
 *
 * Every shell paints a boot spinner inside ``#app`` so a slow
 * connection shows something before the bundle lands. Vue's ``mount``
 * replaced the container's children with the app. Svelte's appends to
 * it, so the spinner has to be cleared here or it stays on top of the
 * page: it is ``position: fixed`` across the whole viewport, so it
 * covers what rendered underneath it and swallows every click.
 *
 * This is the only way anything in this repo mounts, and it lives in
 * ``lib`` rather than beside the public mini-apps because it is not
 * theirs alone. The bug has been shipped twice, once on the public
 * pages and once on the organiser app, both times by an entry that
 * called Svelte's ``mount`` directly.
 */
export function mountApp(component: Component<Record<string, never>>): void {
  const target = document.getElementById("app");
  if (!target) throw new Error("#app is missing");
  target.replaceChildren();
  mount(component, { target });
}
