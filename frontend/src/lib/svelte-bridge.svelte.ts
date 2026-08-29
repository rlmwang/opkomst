import { mount, unmount, type Component } from "svelte";

/**
 * Mount a Svelte component and keep its props live.
 *
 * Svelte reads the props object it was handed and goes on reading it,
 * so the way to push a change through from outside is to mutate that
 * object rather than pass a new one. It has to be ``$state`` for the
 * child to notice, and only a ``.svelte.ts`` module may declare one,
 * which is why this half lives here and the Vue half in
 * ``components/SvelteBridge.vue``.
 *
 * Temporary: it goes when the last Vue component does
 * (``docs/tasks/svelte``).
 */
export function mountBridged(
  target: HTMLElement,
  component: Component<Record<string, unknown>>,
  initial: Record<string, unknown>,
) {
  const props: Record<string, unknown> = $state({ ...initial });
  const instance = mount(component, { target, props });
  return {
    /** Replace what the child sees, key by key, so a prop the parent
     *  stopped passing is removed rather than left at its last value. */
    update(next: Record<string, unknown>): void {
      for (const key of Object.keys(props)) {
        if (!(key in next)) delete props[key];
      }
      Object.assign(props, next);
    },
    destroy(): void {
      void unmount(instance);
    },
  };
}
