import { showToast } from "@/lib/toast";

/**
 * The organiser app's toast API. Was a wrapper over PrimeVue's
 * ``useToast``; the queue underneath is now the app's own
 * (``lib/toast.ts``), which the public mini-apps already used.
 *
 * A composable rather than three loose functions because 27 call sites
 * write ``const toasts = useToasts()`` and none of them should have to
 * change for this.
 */
const LIFE = {
  success: 2000,
  warn: 2500,
  error: 3000,
} as const;

interface ToastOpts {
  detail?: string;
  life?: number;
}

export function useToasts() {
  return {
    success(summary: string, opts: ToastOpts = {}) {
      showToast(summary, { kind: "success", detail: opts.detail, life: opts.life ?? LIFE.success });
    },
    warn(summary: string, opts: ToastOpts = {}) {
      showToast(summary, { kind: "warn", detail: opts.detail, life: opts.life ?? LIFE.warn });
    },
    error(summary: string, opts: ToastOpts = {}) {
      showToast(summary, { kind: "error", detail: opts.detail, life: opts.life ?? LIFE.error });
    },
  };
}
