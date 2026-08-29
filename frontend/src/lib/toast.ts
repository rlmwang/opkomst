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
 * ``App.vue`` and once in ``PublicShell``.
 *
 * The queue itself knows no framework: a plain array and a set of
 * listeners. Each ``AppToast`` subscribes and keeps its own reactive
 * copy, which is what lets a Vue one and a Svelte one read the same
 * queue while the app moves across (``docs/tasks/svelte``).
 */
export type ToastKind = "success" | "warn" | "error";

export interface Toast {
  id: number;
  message: string;
  detail?: string;
  kind?: ToastKind;
}

let toasts: Toast[] = [];
const listeners = new Set<() => void>();
let nextId = 0;

function notify(): void {
  for (const listener of listeners) listener();
}

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
  // A new array rather than a push, so a listener holding the old one
  // can tell that something changed by identity alone.
  toasts = [...toasts, { id, message, detail: opts.detail, kind: opts.kind }];
  notify();
  window.setTimeout(() => {
    toasts = toasts.filter((t) => t.id !== id);
    notify();
  }, opts.life ?? 4000);
}

/** The queue as it stands. */
export function currentToasts(): readonly Toast[] {
  return toasts;
}

/** Hear about every change. Returns the unsubscribe. */
export function subscribeToasts(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}
