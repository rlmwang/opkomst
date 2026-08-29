import type { IconName } from "@/components/app-icons";
import { ask } from "@/lib/confirms.svelte";
import { useToasts } from "@/lib/toasts";

/**
 * "Confirm, then write, then say what happened", in one place.
 *
 * Every destructive action in the app repeated the same shape: ask,
 * await the write, toast the outcome. This is that shape, and the only
 * thing a call site supplies is what to say.
 */
interface ConfirmOpts {
  header: string;
  message: string;
  acceptLabel: string;
  rejectLabel: string;
  /** Optional ``AppIcon`` name for the dialog header icon. */
  icon?: IconName;
}

interface ToastSpec {
  summary: string;
  detail?: string;
}

export interface GuardedSpec<TVars, TResult = unknown> {
  /** The input the write will receive. */
  vars: TVars;
  /** Toast on success. A string is shorthand for ``{ summary }``; a
   *  function receives the result, for count-aware messages. */
  ok: string | ((result: TResult) => string | ToastSpec);
  /** Toast on failure. A string is shorthand; a function receives the
   *  error, so an error class can change the message. */
  fail: string | ((err: unknown) => string);
  /** Optional confirmation before the write runs. */
  confirm?: ConfirmOpts;
}

/** Hands back a function that takes the click-time argument, resolves
 *  the spec, optionally confirms, then writes with toast feedback. */
export function guarded<TArg, TVars, TResult = unknown>(
  write: (vars: TVars) => Promise<TResult>,
  spec: (arg: TArg) => GuardedSpec<TVars, TResult>,
): (arg: TArg) => Promise<void> {
  const toasts = useToasts();

  async function run(s: GuardedSpec<TVars, TResult>): Promise<void> {
    try {
      const result = await write(s.vars);
      const out = typeof s.ok === "function" ? s.ok(result) : s.ok;
      const spoken = typeof out === "string" ? { summary: out } : out;
      toasts.success(spoken.summary, { detail: spoken.detail });
    } catch (err) {
      toasts.error(typeof s.fail === "function" ? s.fail(err) : s.fail);
    }
  }

  return async (arg: TArg): Promise<void> => {
    const s = spec(arg);
    if (!s.confirm) {
      await run(s);
      return;
    }
    ask({ ...s.confirm, accept: () => run(s) });
  };
}
