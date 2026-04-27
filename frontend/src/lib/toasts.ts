import { useToast } from "primevue/usetoast";

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
  const toast = useToast();
  return {
    success(summary: string, opts: ToastOpts = {}) {
      toast.add({ severity: "success", summary, detail: opts.detail, life: opts.life ?? LIFE.success });
    },
    warn(summary: string, opts: ToastOpts = {}) {
      toast.add({ severity: "warn", summary, detail: opts.detail, life: opts.life ?? LIFE.warn });
    },
    error(summary: string, opts: ToastOpts = {}) {
      toast.add({ severity: "error", summary, detail: opts.detail, life: opts.life ?? LIFE.error });
    },
  };
}
