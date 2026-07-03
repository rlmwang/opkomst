import { reactive, readonly } from "vue";

/**
 * A tiny, dependency-free toast for the public mini-apps (they ship no
 * PrimeVue Toast). Client-side validation errors — a missing pseudonym, a
 * malformed email — go here so the visitor gets the *specific* reason,
 * instead of a generic inline "something went wrong". One module-level
 * queue; ``<PublicToast>`` (mounted once in PublicShell) renders it.
 */
interface Toast {
  id: number;
  message: string;
}

const state = reactive<{ toasts: Toast[] }>({ toasts: [] });
let nextId = 0;

/** Show a transient error toast; it auto-dismisses after a few seconds. */
export function showToast(message: string): void {
  const id = ++nextId;
  state.toasts.push({ id, message });
  window.setTimeout(() => {
    const i = state.toasts.findIndex((t) => t.id === id);
    if (i !== -1) state.toasts.splice(i, 1);
  }, 4000);
}

export function usePublicToasts() {
  return readonly(state);
}
