import { reactive, readonly } from "vue";

/**
 * The app's toast queue, shared by the organiser app and the public
 * mini-apps.
 *
 * It began as the public apps' own, because they ship no PrimeVue and
 * needed somewhere for a validation message to go. The organiser app
 * used PrimeVue's Toast next to it, styled through the preset to look
 * the same. This is that one look with one implementation behind it.
 *
 * One module-level queue; ``<AppToast>`` renders it, mounted once in
 * ``App.vue`` and once in ``PublicShell.vue``.
 */
export type ToastKind = "success" | "warn" | "error";

interface Toast {
  id: number;
  message: string;
  detail?: string;
  kind?: ToastKind;
}

const state = reactive<{ toasts: Toast[] }>({ toasts: [] });
let nextId = 0;

interface ShowOpts {
  detail?: string;
  /** Picks the icon. Every kind wears the same colours: colour-coding
   *  three shades of the same message is noise when toasts are this
   *  rare, and the icon already says which it is. */
  kind?: ToastKind;
  life?: number;
}

/** Show a transient toast; it dismisses itself. */
export function showToast(message: string, opts: ShowOpts = {}): void {
  const id = ++nextId;
  state.toasts.push({ id, message, detail: opts.detail, kind: opts.kind });
  window.setTimeout(() => {
    const i = state.toasts.findIndex((t) => t.id === id);
    if (i !== -1) state.toasts.splice(i, 1);
  }, opts.life ?? 4000);
}

export function useToastQueue() {
  return readonly(state);
}
